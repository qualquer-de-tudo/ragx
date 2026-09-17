# ragx trial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ragx trial`, a command that measures — honestly, with the same rigor as `ragx eval` — how many tokens `build_context` actually delivers versus the baseline of reading the whole relevant file(s), over the project's own eval corpus.

**Architecture:** A new `src/ragx/search/trial.py` module reuses `EvalCase`/`load_cases` from the existing `search/evaluation.py` (same corpus format, `tests/eval/queries.yaml`, zero duplication). For each case it computes two numbers with the same `TokenCounter`: the token count of the full content of every file in `relevant_paths` (baseline — what an agent reads without RAGX) and `ContextPack.estimated_tokens` from `build_context` (what RAGX actually hands over). A new `ragx trial` CLI command reports both, the delta, and a coverage check (did the relevant file's content actually make it into the pack, or did RAGX save tokens by dropping the answer?). This is a proxy metric — a full live agent-session replay is out of scope — and the CLI output must say so explicitly, matching this project's existing honesty convention (see `ragx eval`'s "híbrido < keyword" flag).

**Tech Stack:** Python 3.11+, existing `ragx.search.evaluation`, `ragx.context.engine.build_context`, `ragx.tokens`, `typer` (CLI), `pytest` (`integration` marker, same fixture pattern as `tests/integration/test_context.py`).

**Spec:** This plan's own Architecture section above — there is no separate external spec document. Ground truth for existing APIs referenced below is the current source: `src/ragx/search/evaluation.py`, `src/ragx/context/engine.py`, `src/ragx/tokens.py`.

## Global Constraints

- Reuse `EvalCase` / `load_cases` from `src/ragx/search/evaluation.py` — do not duplicate the YAML-loading logic.
- Every path in `relevant_paths` is relative to `cfg.root` (same convention as `evaluation.py` and `tests/eval/queries.yaml`).
- The CLI output must always print the "this is a proxy, not a live session" caveat — never let the number stand alone without it.
- Follow the existing module docstring convention: one dense line + the "why" when non-obvious (see `src/ragx/search/evaluation.py`'s docstring for the exact tone).
- No new third-party dependency. Everything needed (`TokenCounter`, `build_context`, `yaml` via `evaluation.py`) already exists.

---

### Task 1: `TrialResult` and `run_trial()` in `src/ragx/search/trial.py`

**Files:**
- Create: `src/ragx/search/trial.py`
- Test: `tests/integration/test_trial.py`

**Interfaces:**
- Consumes: `ragx.search.evaluation.EvalCase`, `ragx.search.evaluation.load_cases(path: Path) -> list[EvalCase]`; `ragx.context.engine.build_context(cfg: Config, query: str, budget: int | None = None, use_cache: bool = True) -> ContextPack` (returns `.estimated_tokens: int`, `.fragments: tuple[ContextFragment, ...]` where each fragment has `.document_path: str`); `ragx.tokens.get_counter(prefer: str = "auto") -> TokenCounter` (has `.count(text: str) -> int`).
- Produces: `TrialResult` dataclass (fields: `query: str`, `baseline_tokens: int`, `ragx_tokens: int`, `sources_hit: int`, `sources_total: int`) and `run_trial(cfg: Config, cases: list[EvalCase], budget: int = 3000) -> list[TrialResult]`, used by Task 2's CLI command.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_trial.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.search.evaluation import EvalCase
from ragx.search.trial import run_trial

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios contra o provedor SSO corporativo."""

    def login(self, credentials):
        """Valida o token e cria a sessao no Redis com TTL de 30 minutos."""
        session = self.sso.validate(credentials)
        self.redis.setex(session.id, 1800, session.payload)
        return session
'''

LONGO = "# Manual\n\n## Detalhes\n\n" + "\n\n".join(
    f"Paragrafo {i} com bastante texto para gastar bastante espaco de contexto "
    f"e obrigar o motor a comprimir ou descartar alguma coisa." for i in range(120)
)


@pytest.fixture(scope="module")
def proj(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("trial")
    (root / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "manual.md").write_text(LONGO, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


def test_ragx_tokens_never_exceed_budget(proj: Path) -> None:
    cases = [EvalCase(query="autenticacao sessao redis", relevant_paths=("auth.py",))]
    results = run_trial(load_config(proj), cases, budget=500)
    assert results[0].ragx_tokens <= 500


def test_baseline_is_bigger_for_long_file(proj: Path) -> None:
    """O manual grande tem que gerar baseline >> ragx_tokens quando o
    orcamento forca compressao/descarte — e exatamente o efeito que a
    ferramenta existe para medir."""
    cases = [EvalCase(query="detalhes do manual", relevant_paths=("manual.md",))]
    results = run_trial(load_config(proj), cases, budget=300)
    r = results[0]
    assert r.baseline_tokens > r.ragx_tokens
    assert r.sources_total == 1


def test_sources_hit_counts_relevant_paths_in_the_pack(proj: Path) -> None:
    cases = [EvalCase(query="autenticacao sessao redis", relevant_paths=("auth.py",))]
    results = run_trial(load_config(proj), cases, budget=2000)
    assert results[0].sources_hit == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_trial.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ragx.search.trial'`

- [ ] **Step 3: Write minimal implementation**

Create `src/ragx/search/trial.py`:

```python
"""Comparação honesta: tokens que o build_context entrega vs. o baseline de
ler o arquivo inteiro. Mede o que o `ragx eval` não mede — economia real de
tokens, não qualidade de ranking. Reusa o mesmo corpus de `evaluation.py`.

Isto é um proxy, não uma sessão de agente real replayed. Ver docs/07 e o
aviso impresso por `ragx trial`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragx.config import Config
from ragx.context.engine import build_context
from ragx.search.evaluation import EvalCase
from ragx.tokens import get_counter


@dataclass
class TrialResult:
    query: str
    baseline_tokens: int
    ragx_tokens: int
    sources_hit: int
    sources_total: int

    @property
    def saved_tokens(self) -> int:
        return self.baseline_tokens - self.ragx_tokens

    @property
    def saved_ratio(self) -> float:
        if self.baseline_tokens <= 0:
            return 0.0
        return self.saved_tokens / self.baseline_tokens


def run_trial(cfg: Config, cases: list[EvalCase], budget: int = 3000) -> list[TrialResult]:
    counter = get_counter()
    out: list[TrialResult] = []
    for case in cases:
        baseline = 0
        for rel in case.relevant_paths:
            fp = cfg.root / rel
            if fp.is_file():
                baseline += counter.count(fp.read_text(encoding="utf-8", errors="ignore"))
        pack = build_context(cfg, case.query, budget=budget, use_cache=False)
        hit_paths = {f.document_path for f in pack.fragments}
        sources_hit = sum(1 for rel in case.relevant_paths if rel in hit_paths)
        out.append(
            TrialResult(
                query=case.query,
                baseline_tokens=baseline,
                ragx_tokens=pack.estimated_tokens,
                sources_hit=sources_hit,
                sources_total=len(case.relevant_paths),
            )
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_trial.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/ragx/search/trial.py tests/integration/test_trial.py
git commit -m "feat(trial): compara tokens de build_context contra o baseline de ler o arquivo inteiro"
```

---

### Task 2: `ragx trial` CLI command

**Files:**
- Create: `src/ragx/cli/commands/trial_cmd.py`
- Modify: `src/ragx/cli/main.py` (add import + `app.command("trial")` registration, mirroring the existing `eval` registration at line 48: `app.command("eval")(eval_cmd.eval_cmd)`)
- Test: `tests/e2e/test_cli_trial.py`

**Interfaces:**
- Consumes: `run_trial` and `TrialResult` from Task 1 (`ragx.search.trial`); `ragx.search.evaluation.load_cases`; `ragx.config.load_config`.
- Produces: `trial_cmd(...)` function, registered as the `ragx trial` Typer command — no other task depends on this one.

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_cli_trial.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.config import load_config

pytestmark = pytest.mark.e2e

runner = CliRunner()


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text(
        'class AuthService:\n    """Login via SSO."""\n    def login(self):\n        pass\n',
        encoding="utf-8",
    )
    (tmp_path / "queries.yaml").write_text(
        "- query: autenticacao\n  relevant_paths: [\"auth.py\"]\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    return tmp_path


def test_trial_json_reports_savings(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["trial", "--queries", "queries.yaml", "--json"])
    assert result.exit_code == 0, result.output
    assert '"baseline_tokens"' in result.output
    assert '"ragx_tokens"' in result.output


def test_trial_human_output_prints_honesty_caveat(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["trial", "--queries", "queries.yaml"])
    assert result.exit_code == 0, result.output
    assert "proxy" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_cli_trial.py -v`
Expected: FAIL — `No such command 'trial'`

- [ ] **Step 3: Write minimal implementation**

Create `src/ragx/cli/commands/trial_cmd.py`:

```python
"""`ragx trial` — mede tokens de verdade: build_context vs. ler o arquivo inteiro.

Não é uma sessão de agente real reproduzida (isso exigiria instrumentar o
agente em si). É a comparação que dá pra fazer só com o que o RAGX controla —
o mesmo espírito do `ragx eval`, aplicado a economia de tokens em vez de
qualidade de ranking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.search.evaluation import load_cases
from ragx.search.trial import run_trial

console = Console()


def trial_cmd(
    queries: Annotated[Path, typer.Option("--queries")] = Path("tests/eval/queries.yaml"),
    budget: Annotated[int, typer.Option("--budget")] = 3000,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compara tokens do build_context contra o baseline de ler o arquivo inteiro."""
    cfg = load_config()
    path = queries if queries.is_absolute() else cfg.root / queries
    cases = load_cases(path)
    results = run_trial(cfg, cases, budget=budget)

    total_baseline = sum(r.baseline_tokens for r in results)
    total_ragx = sum(r.ragx_tokens for r in results)
    total_hit = sum(r.sources_hit for r in results)
    total_sources = sum(r.sources_total for r in results)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "budget": budget,
                    "cases": len(results),
                    "results": [
                        {
                            "query": r.query,
                            "baseline_tokens": r.baseline_tokens,
                            "ragx_tokens": r.ragx_tokens,
                            "saved_tokens": r.saved_tokens,
                            "saved_ratio": round(r.saved_ratio, 4),
                            "sources_hit": r.sources_hit,
                            "sources_total": r.sources_total,
                        }
                        for r in results
                    ],
                    "totals": {
                        "baseline_tokens": total_baseline,
                        "ragx_tokens": total_ragx,
                        "saved_ratio": round(
                            (total_baseline - total_ragx) / total_baseline, 4
                        )
                        if total_baseline
                        else 0.0,
                        "source_coverage": round(total_hit / total_sources, 4)
                        if total_sources
                        else 0.0,
                    },
                },
                ensure_ascii=False,
            )
        )
        return

    console.print(f"\n[bold]Trial de tokens[/] — {len(results)} consultas, orçamento {budget}\n")
    console.print(f"  {'Consulta':<40}{'Baseline':>10}{'RAGX':>8}{'Economia':>10}{'Fonte':>7}")
    console.print(f"  {'-' * 77}")
    for r in results:
        economia = f"{r.saved_ratio:.0%}"
        fonte = f"{r.sources_hit}/{r.sources_total}"
        console.print(
            f"  {r.query[:38]:<40}{r.baseline_tokens:>10}{r.ragx_tokens:>8}{economia:>10}{fonte:>7}"
        )

    coverage = total_hit / total_sources if total_sources else 0.0
    saved = (total_baseline - total_ragx) / total_baseline if total_baseline else 0.0
    console.print(f"\n  Total: {saved:.0%} menos tokens · fonte relevante coberta em {coverage:.0%} dos casos")
    console.print(
        "\n  [dim]Isto é um proxy — compara com \"ler o arquivo inteiro\", não com uma "
        "sessão de agente real. Se a cobertura de fonte cair muito, a economia de "
        "token não vale nada: RAGX estaria economizando tokens jogando fora a resposta.[/]\n"
    )
```

Modify `src/ragx/cli/main.py`: add `trial_cmd` to the import block (near line 17, alongside `eval_cmd`) and add the registration line near line 48:

```python
app.command("trial")(trial_cmd.trial_cmd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_cli_trial.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/ragx/cli/commands/trial_cmd.py src/ragx/cli/main.py tests/e2e/test_cli_trial.py
git commit -m "feat(cli): adiciona ragx trial"
```

---

### Task 3: Documentar o método e o limite

**Files:**
- Modify: `docs/07-context-engine.md` (add a "Trial — economia de tokens" section)
- Modify: `docs/14-cli.md` (add `ragx trial` to the command reference table)
- Modify: `AGENTS.md` (add `ragx trial` to the quick-orientation commands, right after the existing `ragx context` example)

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by other tasks — this is the terminal task of the plan.

- [ ] **Step 1: Add the section to `docs/07-context-engine.md`**

Append at the end of the file:

```markdown
## Trial — economia de tokens (honesta)

```bash
ragx trial                          # usa tests/eval/queries.yaml
ragx trial --budget 1500 --json
```

Para cada consulta do corpus de avaliação, compara dois números medidos com o
mesmo `TokenCounter`:

- **baseline** — tokens do conteúdo INTEIRO de cada arquivo em `relevant_paths`
  (o que um agente leria sem o RAGX);
- **ragx** — `estimated_tokens` do `ContextPack` que o `build_context` entrega
  para o mesmo orçamento.

**O que isto NÃO é**: uma sessão de agente real reproduzida com e sem RAGX.
É um proxy — mede o que o RAGX controla (o tamanho do que ele entrega), não o
que o agente realmente teria lido sozinho. Por isso `ragx trial` sempre reporta
também a **cobertura de fonte** (`sources_hit / sources_total`): economia de
token sem a fonte relevante dentro do pacote não é economia, é perda de
informação disfarçada de otimização.
```

- [ ] **Step 2: Add the row to `docs/14-cli.md`**

Find the command reference table and add a row for `trial` in the same format as the existing `eval` row (open the file first to match the exact table syntax already there before inserting).

- [ ] **Step 3: Add to `AGENTS.md`**

In the "Orientação rápida" code block that currently ends with `ragx context "sua tarefa" --tokens 3000`, add one more line right after it:

```
ragx trial                                    # prova, no seu corpus, se o build_context economiza token de verdade
```

- [ ] **Step 4: Commit**

```bash
git add docs/07-context-engine.md docs/14-cli.md AGENTS.md
git commit -m "docs: documenta ragx trial e seus limites"
```

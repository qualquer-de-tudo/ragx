# Telemetria MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every MCP tool call writes one line to `.ragx/logs/mcp.jsonl` (tool, latency, project — finally implementing what `docs/09-mcp.md` already documents but the code never built), `build_context` calls additionally record `tokens_delivered`, and `ragx init` auto-registers the project into the machine hub.

**Architecture:** All ~20 MCP tools already funnel through one function, `_guarded()` in `src/ragx/mcp/server.py:52`. Extending that single function is the entire instrumentation surface — no per-tool changes needed. `ragx init` gets one best-effort call to the hub's existing `register()` function at the end of its existing flow.

**Tech Stack:** Python 3.11+, stdlib only (`pathlib`, `json`, `time`) — no new dependency.

**Spec:** `docs/superpowers/specs/2026-09-21-painel-desktop-design.md`, section "Parte 1 — Telemetria real no RAGX".

## Global Constraints

- No new third-party dependency (spec: "Tech Stack: stdlib only").
- Never log query text or arguments — only `tool`, `ms`, `project`, and (for `build_context` only) `tokens_delivered` (spec: "Grava a query/argumentos? Não").
- Log a line even when the tool call fails (spec: "Escreve mesmo quando a ferramenta falha? Sim").
- `ragx init` must never fail because hub registration failed (spec: "best-effort, nunca falha o init").
- No log rotation in this version (spec: explicitly out of scope).

---

### Task 1: `_log_call` and wiring it into `_guarded`

**Files:**
- Modify: `src/ragx/mcp/server.py:1-10` (imports), `src/ragx/mcp/server.py:52-86` (`_guarded`)
- Test: `tests/integration/test_mcp_telemetry.py`

**Interfaces:**
- Produces: `_log_call(cfg: Config, tool: str, started_at: float, result: Any) -> None` (module-private function in `server.py`), called from inside `_guarded`. No other task depends on this function directly — Task 2 (hub registration) is independent and touches a different file.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_mcp_telemetry.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.mcp.server import build_server

pytestmark = pytest.mark.integration


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
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    return tmp_path


def _log_lines(proj: Path) -> list[dict]:
    log_path = proj / ".ragx" / "logs" / "mcp.jsonl"
    if not log_path.is_file():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _call_tool(cfg, name: str, **kwargs):
    server = build_server(cfg, allow_write=False)
    tools = {t.name: t for t in await server.list_tools()}
    assert name in tools
    return await server.call_tool(name, kwargs)


def test_successful_call_logs_tool_and_ms(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "get_dictionary"))

    lines = _log_lines(proj)
    assert len(lines) == 1
    assert lines[0]["tool"] == "get_dictionary"
    assert isinstance(lines[0]["ms"], (int, float))
    assert lines[0]["ms"] >= 0
    assert "project" in lines[0]
    assert "tokens_delivered" not in lines[0]


def test_build_context_logs_tokens_delivered(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "build_context", query="login sso", tokens=500))

    lines = _log_lines(proj)
    matching = [l for l in lines if l["tool"] == "build_context"]
    assert len(matching) == 1
    assert isinstance(matching[0]["tokens_delivered"], int)


def test_failed_call_still_logs(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    # get_chunk com id inexistente -> falha tratada (ok: false), nao excecao crua
    asyncio.run(_call_tool(cfg, "get_chunk", chunk_id="nao-existe"))

    lines = _log_lines(proj)
    assert len(lines) == 1
    assert lines[0]["tool"] == "get_chunk"
```

Note: if `server.list_tools()`/`server.call_tool()` aren't the exact async
API this MCP SDK version exposes, check `tests/` for an existing test that
already calls a tool through `build_server()` (search `build_server` in
`tests/`) and match that test's actual call pattern instead — do not guess
at the SDK's method names.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_mcp_telemetry.py -v`
Expected: FAIL — no `.ragx/logs/mcp.jsonl` file is created (0 lines instead of 1)

- [ ] **Step 3: Write minimal implementation**

In `src/ragx/mcp/server.py`, add to the existing top-of-file imports (near
the other stdlib imports — read the current import block first and add
alongside it, don't create a second import block):

```python
import time
```

Replace `_guarded` (currently `src/ragx/mcp/server.py:52-86`) with:

```python
def _guarded(fn: Any, tool: str, cfg: Config) -> Any:
    """Falha de ferramenta vira erro ESTRUTURADO, não exceção crua.

    Sem isto o agente recebe "Error executing tool X" — uma string sem código,
    sem causa e sem nada acionável. O detalhe vai para o log; o agente recebe
    o suficiente para decidir o que fazer.
    """
    inicio = time.monotonic()
    try:
        resultado = fn()
        _log_call(cfg, tool, inicio, resultado)
        return resultado
    except ValidationError as exc:
        # Argumento fora do contrato é erro de QUEM CHAMOU, não falha interna.
        # Tratá-lo como `internal` mandava o agente (e a extensão do VS Code)
        # caçar num log de traceback o que a própria mensagem já sabe dizer:
        # qual campo, qual limite, qual valor veio. Quem recebe "ValidationError.
        # Detalhe em .ragx/logs/errors.log" não tem como corrigir a chamada.
        return err("invalid_argument", f"{tool}: {_explain(exc)}")
    except Exception as exc:
        # "Ainda não há índice aqui" NÃO é falha interna: é o estado normal de
        # toda pasta que não é um projeto RAGX. Com o servidor registrado
        # globalmente, isso acontece em boa parte das sessões — e responder
        # `internal` mandando olhar um log que não existe faz o agente concluir
        # que o RAGX está quebrado.
        if not cfg.db_path.exists():
            return err(
                "not_indexed",
                f"nenhum índice em {cfg.root}. Se este é o projeto certo, rode "
                f"`ragx init && ragx index .` na raiz dele; se não, abra a "
                f"sessão dentro de um projeto já indexado.",
            )
        log_exception(cfg.state_dir, tool, exc)
        return err(
            "internal",
            f"{tool} falhou: {type(exc).__name__}. "
            "Detalhe em .ragx/logs/errors.log",
        )


def _log_call(cfg: Config, tool: str, started_at: float, result: Any) -> None:
    """Telemetria de uso — uma linha por chamada, nunca a query/argumentos.

    O agente decide sozinho quando reindexar; isto é o que deixa visível,
    depois, o que ele de fato chamou e quanto cada chamada custou.
    """
    ms = round((time.monotonic() - started_at) * 1000, 1)
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "ms": ms,
        "project": cfg.project.name,
    }
    if tool == "build_context" and isinstance(result, dict) and result.get("ok"):
        tokens = (result.get("data") or {}).get("estimated_tokens")
        if isinstance(tokens, int):
            entry["tokens_delivered"] = tokens

    log_dir = cfg.state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "mcp.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

Add `datetime`/`timezone` and `json` to the imports if not already present
in `server.py` (read the current import block first — `json` is very likely
already imported given `err`/`ok` helpers in the same file; only add what's
actually missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_mcp_telemetry.py -v`
Expected: 3 passed

- [ ] **Step 5: Confirm the architectural test still passes**

Run: `uv run pytest tests/security -k architect -v` (or, if that filter
matches nothing, search for the actual test name first: `grep -rl "mcp.*nao.*importa\|architect" tests/` and run that file directly)
Expected: still passes — `_log_call` only uses `pathlib`/`json`/`time`/`datetime`, already-permitted stdlib in `ragx.mcp`.

- [ ] **Step 6: Run the full fast suite**

Run: `uv run pytest -m "not slow"`
Expected: all passing, no regressions

- [ ] **Step 7: Commit**

```bash
git add src/ragx/mcp/server.py tests/integration/test_mcp_telemetry.py
git commit -m "feat(mcp): loga cada chamada MCP em .ragx/logs/mcp.jsonl"
```

---

### Task 2: `ragx init` auto-registra no hub

**Files:**
- Modify: `src/ragx/cli/commands/init.py` (end of the `init()` function)
- Test: `tests/e2e/test_cli_fase0.py` (add to existing file — search for
  existing `init`-related tests there to match their fixture style; if none
  exist, use the `CliRunner` pattern already established elsewhere in the
  same file)

**Interfaces:**
- Consumes: `ragx.federation.hub.register(cfg: Config, path: Path | None = None, name: str | None = None, from_federation: Path | None = None, visibility: str | None = None) -> ProjectRef` — already exists, `src/ragx/federation/hub.py:89`. Raises `UsageError` when the project is `visibility = "private"` or has no `ragx.toml`.
- Produces: nothing new consumed by other tasks — this is independent of Task 1.

- [ ] **Step 1: Write the failing test**

Read `tests/e2e/test_cli_fase0.py`'s existing fixture/imports first (it
already has `CliRunner`/`app` set up from earlier plans in this session —
match its exact style). Add:

```python
def test_init_registra_projeto_no_hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isola o HOME para nao escrever no hub real da maquina rodando o teste.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows

    proj_dir = tmp_path / "meu-projeto"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output

    from ragx.config import load_config
    from ragx.federation import hub

    cfg = load_config(proj_dir)
    projetos = hub.list_projects(cfg)
    assert len(projetos) == 1
    assert projetos[0]["path"] == str(proj_dir.resolve())


def test_init_nao_falha_se_projeto_e_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    proj_dir = tmp_path / "projeto-privado"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    # marca como private DEPOIS do init (init cria o ragx.toml default)
    cfg_path = proj_dir / "ragx.toml"
    texto = cfg_path.read_text(encoding="utf-8").replace(
        'visibility = "workspace"', 'visibility = "private"'
    )
    cfg_path.write_text(texto, encoding="utf-8")

    # rodar init de novo (idempotente) nao deve quebrar mesmo com o projeto private
    result2 = runner.invoke(app, ["init", "--force"])
    assert result2.exit_code == 0, result2.output
```

Check the file's config-writing convention in the existing `init()`
implementation (Step 3 below) before assuming the exact TOML text to
replace — match what `init.py` actually writes.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_cli_fase0.py -k "registra_projeto_no_hub or nao_falha_se_projeto_e_private" -v`
Expected: FAIL — `hub.list_projects(cfg)` returns an empty list (init never called `register`)

- [ ] **Step 3: Write minimal implementation**

Read `src/ragx/cli/commands/init.py`'s current `init()` function in full
first (it ends around the `console.print("\nPróximo passo: ...")` line) to
find the exact final lines before adding this — the plan shows the addition,
not the whole function, since the file already exists and this is an
append near the end, not a rewrite:

```python
    from ragx.federation import hub as hub_mod
    from ragx.core.errors import UsageError

    try:
        hub_mod.register(cfg, path=root)
        console.print(f"  [dim]registrado no hub ({cfg.hub_dir})[/]")
    except UsageError:
        # Projeto private, ou (raro) ragx.toml sumiu entre a escrita acima e
        # aqui: registro no hub é um extra, nao motivo pra falhar o init.
        pass
```

Place this right before the final `console.print("\nPróximo passo: ...")`
line, so the "próximo passo" message stays the last thing printed.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_cli_fase0.py -k "registra_projeto_no_hub or nao_falha_se_projeto_e_private" -v`
Expected: 2 passed

- [ ] **Step 5: Run the full fast suite**

Run: `uv run pytest -m "not slow"`
Expected: all passing — in particular, re-check any existing `ragx init`
test in `tests/` that asserts on `init`'s exact stdout doesn't break from
the new `"registrado no hub"` line; if one does, that's an expected,
correct update to that assertion, not a regression.

- [ ] **Step 6: Commit**

```bash
git add src/ragx/cli/commands/init.py tests/e2e/test_cli_fase0.py
git commit -m "feat(init): registra o projeto no hub automaticamente"
```

---

### Task 3: Documentar

**Files:**
- Modify: `docs/09-mcp.md` (the existing "Observabilidade" section — it
  currently describes the log format as if already implemented; correct
  any wording that implies otherwise, and confirm the sample line's field
  names match Task 1's actual output)
- Modify: `docs/14-cli.md` (the `ragx init` command reference, if it
  describes what `init` does — add the hub registration line)
- Modify: `AGENTS.md` (if it mentions hub registration as a manual-only
  step anywhere — check `docs/17-multiprojeto-e-federacao.md` too, since
  that's the doc most likely to say "registre com `ragx project register`"
  as the ONLY way to join the hub; correct it to mention automatic
  registration on `init` now)

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing.

- [ ] **Step 1: Read the current content of all three files' relevant sections first**

Do not guess at current wording — read `docs/09-mcp.md`'s Observabilidade
section, `docs/14-cli.md`'s init reference, and `docs/17-multiprojeto-e-federacao.md`'s registration section before editing any of them.

- [ ] **Step 2: Update `docs/09-mcp.md`**

Confirm the sample JSON line matches Task 1's actual fields
(`ts`, `tool`, `ms`, `project`, optional `tokens_delivered`) — update the
example if it currently shows different fields (e.g. `hits`, `query_hash`,
which Task 1 does NOT implement per the spec's explicit "não grava
query/argumentos" decision).

- [ ] **Step 3: Update `docs/14-cli.md` and `docs/17-multiprojeto-e-federacao.md`**

Add one line each noting `ragx init` now registers automatically (best
-effort) into the hub, and `ragx project register` remains the way to
register a project that predates this change, or one marked `private` that
the user later wants to opt in manually with a different visibility.

- [ ] **Step 4: Commit**

```bash
git add docs/09-mcp.md docs/14-cli.md docs/17-multiprojeto-e-federacao.md
git commit -m "docs: telemetria MCP real e registro automatico no hub"
```

"""Harness de A/B de economia: as mesmas tarefas, com e sem o RAGX (RAGX-0162, S14).

"O RAGX economiza X%" não é afirmável sem medir: o baseline do painel e do `ragx trial` é o arquivo
inteiro (`size_bytes/4`), e um agente com `Grep` não leria 16 arquivos inteiros. A única medição honesta é
um A/B: cada tarefa roda por `claude -p` em braços (`without`: sem MCP; `full` e `slim`: o servidor do RAGX
em cada perfil), com o MESMO modelo e as MESMAS ferramentas nativas, e se compara o consumo que o próprio
Claude Code reporta, só nas tarefas em que os dois braços ACHARAM o arquivo certo (economia sem acerto não
conta, a mesma lógica da cobertura de fonte do `trial`).

Este módulo é o harness. Ele NÃO roda nada por conta própria: `dry_run` só imprime o plano, `SimulatedRunner`
gera números determinísticos (marcados `simulated`, nunca apresentados como economia real) e o
`ClaudeRunner` só é chamado quando a pessoa pede `ragx ab --execute` com as guardas de custo.

Não persiste o TEXTO da resposta: só `hit`, os caminhos citados e contagens.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ragx.procs import run_quiet

ARMS = ("without", "full", "slim")

PROMPT = (
    "Responda SOMENTE com os caminhos relativos dos arquivos deste projeto que respondem à pergunta, "
    "um por linha, sem explicação.\n\nPergunta: {query}"
)

#: Menos tarefas do que isto: o resultado é rotulado inconclusivo.
MIN_TASKS = 10

_PATH = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]{1,6}")


@dataclass(frozen=True)
class AbTask:
    query: str
    relevant_paths: tuple[str, ...]


@dataclass(frozen=True)
class Call:
    """Uma chamada planejada: braço, tarefa, repetição e o `argv` exato (sem executar nada)."""

    arm: str
    task_index: int
    rep: int
    task: AbTask
    argv: tuple[str, ...]
    prompt: str


@dataclass
class ArmResult:
    arm: str
    task_index: int
    rep: int
    hit: bool = False
    cited_paths: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    turns: int = 0
    duration_ms: int = 0
    ragx_calls: int = 0
    ragx_resp_tokens: int = 0
    simulated: bool = False
    error: str | None = None

    @property
    def billable(self) -> int:
        """Tokens faturáveis (sem o `cache_read`, que custa uma fração): a manchete do relatório."""
        return self.input_tokens + self.cache_creation_tokens + self.output_tokens

    @property
    def gross(self) -> int:
        return self.billable + self.cache_read_tokens


class Runner(Protocol):
    simulated: bool

    def version(self) -> str | None: ...

    def run(self, call: Call) -> ArmResult: ...


# ── o plano ─────────────────────────────────────────────────────────────
def order_for(task_index: int, arms: Sequence[str]) -> list[str]:
    """A ordem dos braços gira por tarefa: nenhum braço é sempre o primeiro (cache aquecido, cota)."""
    arms = list(arms)
    k = task_index % len(arms) if arms else 0
    return arms[k:] + arms[:k]


def mcp_config(arm: str, root: Path) -> dict[str, Any]:
    """O JSON de `--mcp-config` do braço. `without`: nenhum servidor (com `--strict-mcp-config`)."""
    if arm == "without":
        return {"mcpServers": {}}
    return {
        "mcpServers": {
            "ragx": {
                "command": sys.executable,
                "args": ["-m", "ragx.cli.main", "mcp", "serve", "--project", str(root)],
                "env": {"RAGX_MCP_PROFILE": arm},
            }
        }
    }


def build_argv(
    arm: str,
    mcp_file: Path,
    *,
    claude: str = "claude",
    model: str | None = None,
    max_turns: int | None = None,
    isolate: bool = False,
) -> tuple[str, ...]:
    """O `argv` de uma chamada. O prompt NÃO entra aqui: vai pelo stdin (`claude -p` lê dele), o que
    dispensa citar aspas e quebras de linha no `claude.cmd` do Windows."""
    argv = [claude, "-p", "--output-format", "json", "--no-session-persistence",
            "--strict-mcp-config", "--mcp-config", str(mcp_file)]
    if model:
        argv += ["--model", model]
    if max_turns:
        argv += ["--max-turns", str(max_turns)]
    if isolate:
        argv.append("--bare")  # sem hooks nem CLAUDE.md; exige ANTHROPIC_API_KEY (ver `claude --help`)
    return tuple(argv)


def plan(
    tasks: Sequence[AbTask],
    arms: Sequence[str],
    reps: int,
    root: Path,
    out_dir: Path,
    **flags: Any,
) -> list[Call]:
    """Todas as chamadas, na ordem em que rodariam. Não escreve nada: o JSON de `--mcp-config` fica
    em `out_dir/<braço>.mcp.json` e só é gravado por `write_mcp_files` na hora de executar."""
    calls: list[Call] = []
    for i, task in enumerate(tasks):
        for rep in range(reps):
            for arm in order_for(i + rep, arms):
                argv = build_argv(arm, out_dir / f"{arm}.mcp.json", **flags)
                calls.append(Call(arm, i, rep, task, argv, PROMPT.format(query=task.query)))
    return calls


def write_mcp_files(arms: Sequence[str], root: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        (out_dir / f"{arm}.mcp.json").write_text(
            json.dumps(mcp_config(arm, root), ensure_ascii=False, indent=1), encoding="utf-8"
        )


# ── acerto ──────────────────────────────────────────────────────────────
def _norm(caminho: str) -> str:
    texto = caminho.replace("\\", "/").strip().lower()
    while texto.startswith("./"):  # só o prefixo `./`: `.github/` mantém o ponto
        texto = texto[2:]
    return texto


def cited_paths(text: str, limit: int = 30) -> list[str]:
    """Os tokens com cara de caminho que a resposta cita (sem o texto em volta)."""
    vistos: dict[str, None] = {}
    for m in _PATH.finditer(text or ""):
        vistos.setdefault(_norm(m.group(0)), None)
        if len(vistos) >= limit:
            break
    return list(vistos)


def is_hit(text: str, relevant: Sequence[str]) -> bool:
    """Algum caminho relevante citado na resposta. Comparação de texto, determinística."""
    corpo = _norm(text or "")
    return any(_norm(r) in corpo for r in relevant)


# ── os executores ───────────────────────────────────────────────────────
class ClaudeRunner:
    """Roda `claude -p`. SÓ é usado por `ragx ab --execute` (cada chamada gasta cota da conta)."""

    simulated = False

    def __init__(self, claude: str | None = None, timeout_s: float = 600.0, mcp_log: Path | None = None):
        self.claude = claude or shutil.which("claude") or "claude"
        self.timeout_s = timeout_s
        self.mcp_log = mcp_log

    def version(self) -> str | None:
        try:
            out = run_quiet(
                [self.claude, "--version"], capture_output=True, text=True, encoding="utf-8",
                timeout=30, check=False,
            )
            return out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None

    def run(self, call: Call) -> ArmResult:
        res = ArmResult(call.arm, call.task_index, call.rep)
        antes = _mcp_log_size(self.mcp_log)
        t0 = time.time()
        try:
            proc = run_quiet(
                list(call.argv), input=call.prompt, capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout_s, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            res.error = f"{type(exc).__name__}: {exc}"
            return res
        if proc.returncode != 0:
            res.error = f"claude saiu com {proc.returncode}"
        try:
            dados = json.loads(proc.stdout)
        except ValueError:
            res.error = res.error or "saída não é JSON"
            return res
        _preencher(res, dados, call.task)
        res.duration_ms = res.duration_ms or int((time.time() - t0) * 1000)
        res.ragx_calls, res.ragx_resp_tokens = _mcp_log_delta(self.mcp_log, antes)
        return res


def _preencher(res: ArmResult, dados: dict[str, Any], task: AbTask) -> None:
    """Campos do JSON de `claude -p --output-format json`. O texto da resposta NÃO é guardado."""
    texto = str(dados.get("result") or "")
    res.hit = is_hit(texto, task.relevant_paths)
    res.cited_paths = cited_paths(texto)
    uso = dados.get("usage") or {}
    res.input_tokens = int(uso.get("input_tokens") or 0)
    res.output_tokens = int(uso.get("output_tokens") or 0)
    res.cache_creation_tokens = int(uso.get("cache_creation_input_tokens") or 0)
    res.cache_read_tokens = int(uso.get("cache_read_input_tokens") or 0)
    res.cost_usd = float(dados.get("total_cost_usd") or 0.0)
    res.turns = int(dados.get("num_turns") or 0)
    res.duration_ms = int(dados.get("duration_ms") or 0)
    if dados.get("is_error"):
        res.error = res.error or "o Claude Code reportou erro"


def _mcp_log_size(path: Path | None) -> int:
    try:
        return path.stat().st_size if path is not None else 0
    except OSError:
        return 0


def _mcp_log_delta(path: Path | None, antes: int) -> tuple[int, int]:
    """Chamadas ao RAGX e `resp_tokens` gravados no `mcp.jsonl` DESDE `antes` (RAGX-0156): serve para
    calibrar o contador heurístico contra o `usage` de verdade."""
    if path is None:
        return 0, 0
    try:
        with path.open("rb") as fh:
            fh.seek(antes)
            linhas = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return 0, 0
    n = tokens = 0
    for linha in linhas:
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        n += 1
        tokens += int(e.get("resp_tokens") or 0)
    return n, tokens


class SimulatedRunner:
    """Números determinísticos por semente, para testar o harness sem gastar cota. NUNCA é economia real."""

    simulated = True

    def __init__(self, seed: int = 0):
        self.seed = seed

    def version(self) -> str | None:
        return "simulado"

    def run(self, call: Call) -> ArmResult:
        h = hashlib.sha256(f"{self.seed}|{call.arm}|{call.task.query}|{call.rep}".encode()).digest()
        rng = random.Random(int.from_bytes(h[:8], "big"))
        base = {"without": 42_000, "full": 31_000, "slim": 27_000}.get(call.arm, 40_000)
        res = ArmResult(call.arm, call.task_index, call.rep, simulated=True)
        res.hit = rng.random() < 0.85
        res.cited_paths = list(call.task.relevant_paths[:1]) if res.hit else []
        res.input_tokens = int(base * rng.uniform(0.15, 0.25))
        res.cache_creation_tokens = int(base * rng.uniform(0.2, 0.3))
        res.cache_read_tokens = int(base * rng.uniform(1.0, 2.0))
        res.output_tokens = rng.randint(150, 600)
        res.cost_usd = round(res.billable * 8e-6, 4)
        res.turns = rng.randint(3, 9)
        res.duration_ms = rng.randint(8_000, 40_000)
        res.ragx_calls = 0 if call.arm == "without" else rng.randint(1, 4)
        return res


# ── a estatística ───────────────────────────────────────────────────────
def quartiles(valores: Sequence[float]) -> tuple[float, float, float]:
    if not valores:
        return (0.0, 0.0, 0.0)
    v = sorted(valores)
    if len(v) == 1:
        return (v[0], v[0], v[0])
    q = statistics.quantiles(v, n=4, method="inclusive")
    return (q[0], statistics.median(v), q[2])


def bootstrap_ci(valores: Sequence[float], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Intervalo de 95% da mediana por bootstrap, com semente fixa: o mesmo dado dá o mesmo intervalo."""
    if not valores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(valores)
    medianas = sorted(statistics.median(rng.choices(valores, k=k)) for _ in range(n))
    return (medianas[int(0.025 * n)], medianas[int(0.975 * n) - 1])


def paired_savings(results: Sequence[ArmResult], base: str, arm: str) -> list[float]:
    """Economia relativa de `arm` contra `base`, por (tarefa, repetição), SÓ onde os dois acharam o arquivo."""
    por_chave: dict[tuple[int, int], dict[str, ArmResult]] = {}
    for r in results:
        if r.error is None:
            por_chave.setdefault((r.task_index, r.rep), {})[r.arm] = r
    economias: list[float] = []
    for pares in por_chave.values():
        a, b = pares.get(base), pares.get(arm)
        if a is None or b is None or not (a.hit and b.hit) or a.billable <= 0:
            continue
        economias.append((a.billable - b.billable) / a.billable)
    return economias


def summarize(results: Sequence[ArmResult], arms: Sequence[str], n_tasks: int) -> dict[str, Any]:
    por_braco: dict[str, Any] = {}
    for arm in arms:
        rs = [r for r in results if r.arm == arm]
        ok = [r for r in rs if r.error is None]
        por_braco[arm] = {
            "calls": len(rs),
            "errors": len(rs) - len(ok),
            "hit_rate": round(sum(r.hit for r in ok) / len(ok), 3) if ok else None,
            "billable_tokens_median": statistics.median([r.billable for r in ok]) if ok else None,
            "gross_tokens_median": statistics.median([r.gross for r in ok]) if ok else None,
            "cost_usd_median": round(statistics.median([r.cost_usd for r in ok]), 4) if ok else None,
            "turns_median": statistics.median([r.turns for r in ok]) if ok else None,
        }
    comparacoes: dict[str, Any] = {}
    if "without" in arms:
        for arm in arms:
            if arm == "without":
                continue
            e = paired_savings(results, "without", arm)
            q1, med, q3 = quartiles(e)
            lo, hi = bootstrap_ci(e)
            inconclusivo = n_tasks < MIN_TASKS or not e or (lo <= 0.0 <= hi)
            comparacoes[f"{arm}_vs_without"] = {
                "pairs": len(e),
                "saving_median": round(med, 4),
                "saving_q1": round(q1, 4),
                "saving_q3": round(q3, 4),
                "ci95": [round(lo, 4), round(hi, 4)],
                "label": "inconclusivo" if inconclusivo else ("economiza" if med > 0 else "não economiza"),
            }
    return {"arms": por_braco, "comparisons": comparacoes}


@dataclass
class AbReport:
    method: dict[str, Any]
    summary: dict[str, Any]
    results: list[dict[str, Any]]
    simulated: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "simulated": self.simulated,
            "method": self.method,
            "summary": self.summary,
            "results": self.results,
        }


def run_ab(
    calls: Sequence[Call], runner: Runner, arms: Sequence[str], n_tasks: int, method: dict[str, Any]
) -> AbReport:
    """Executa o plano com `runner` e monta o relatório. Quem decide se pode rodar é a CLI."""
    resultados = [runner.run(c) for c in calls]
    metodo = {**method, "claude_version": runner.version(), "simulated": runner.simulated}
    return AbReport(
        method=metodo,
        summary=summarize(resultados, arms, n_tasks),
        results=[asdict(r) for r in resultados],
        simulated=runner.simulated,
    )

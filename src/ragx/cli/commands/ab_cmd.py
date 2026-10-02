"""`ragx ab` — o A/B de economia: as mesmas tarefas, com e sem o RAGX (RAGX-0162).

Por padrão NÃO executa nada: `--dry-run` imprime as chamadas planejadas e o total. `--simulate` roda o
harness de ponta a ponta com números sintéticos (marcados `simulated`). `--execute` roda `claude -p` DE
VERDADE, gasta a cota da sua conta e por isso só vale com `RAGX_AB_REAL=1` e `--max-calls N`.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()


def ab(
    arms: Annotated[str, typer.Option("--arms", help="Braços, separados por vírgula: without,full,slim.")] = "without,full,slim",
    reps: Annotated[int, typer.Option("--reps", min=1, help="Repetições por tarefa e braço.")] = 1,
    model: Annotated[str | None, typer.Option("--model", help="O MESMO modelo em todos os braços.")] = None,
    max_turns: Annotated[int | None, typer.Option("--max-turns", help="O mesmo teto de turnos em todos os braços.")] = None,
    queries: Annotated[Path | None, typer.Option("--queries", help="YAML de consultas (padrão: tests/eval/queries.yaml, ou geradas do índice).")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Quantas tarefas usar.")] = 12,
    out: Annotated[Path | None, typer.Option("--out", help="Pasta do relatório (padrão: .ragx/ab).")] = None,
    isolate: Annotated[bool, typer.Option("--isolate", help="Passa `--bare` ao claude: sem hooks nem CLAUDE.md (exige ANTHROPIC_API_KEY).")] = False,
    simulate: Annotated[bool, typer.Option("--simulate", help="Roda o harness com números SINTÉTICOS (não é economia real).")] = False,
    execute: Annotated[bool, typer.Option("--execute", help="Roda `claude -p` de verdade (gasta cota): exige RAGX_AB_REAL=1 e --max-calls.")] = False,
    max_calls: Annotated[int | None, typer.Option("--max-calls", help="Teto de chamadas reais (obrigatório com --execute).")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mede a economia real do RAGX contra um agente sem ele (padrão: só mostra o plano)."""
    from ragx.search import ab as harness
    from ragx.search.evaluation import load_cases
    from ragx.search.trial import auto_cases

    cfg = load_config()
    escolhidos = [a.strip() for a in arms.split(",") if a.strip()]
    invalidos = [a for a in escolhidos if a not in harness.ARMS]
    if invalidos or not escolhidos:
        raise UsageError(f"braço inválido: {invalidos or arms!r} (use {', '.join(harness.ARMS)})")
    if simulate and execute:
        raise UsageError("use --simulate OU --execute, não os dois")

    caminho = queries or (cfg.root / "tests" / "eval" / "queries.yaml")
    if caminho.is_file():
        casos = load_cases(caminho, only_answerable=True)
    elif cfg.db_path.exists():
        casos = auto_cases(cfg, limit=limit)
    else:
        raise UsageError("sem consultas: passe --queries ou indexe o projeto (`ragx index .`)")
    tarefas = [harness.AbTask(c.query, tuple(c.relevant_paths)) for c in casos[:limit]]
    if not tarefas:
        raise UsageError("nenhuma tarefa para medir")

    pasta = out or (cfg.state_dir / "ab")
    claude = shutil.which("claude") or "claude"
    chamadas = harness.plan(
        tarefas, escolhidos, reps, cfg.root, pasta / "tmp",
        claude=claude, model=model, max_turns=max_turns, isolate=isolate,
    )

    if not simulate and not execute:
        _plano(chamadas, escolhidos, tarefas, reps, as_json)
        return

    if execute:
        _guardas(chamadas, max_calls)
        runner: Any = harness.ClaudeRunner(claude, mcp_log=cfg.state_dir / "logs" / "mcp.jsonl")
        harness.write_mcp_files(escolhidos, cfg.root, pasta / "tmp")
    else:
        runner = harness.SimulatedRunner()

    metodo = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "max_turns": max_turns,
        "isolate": isolate,
        "arms": escolhidos,
        "tasks": len(tarefas),
        "reps": reps,
        "calls": len(chamadas),
        "profile_by_arm": {a: ("none" if a == "without" else a) for a in escolhidos},
        "commit": None if simulate else _commit(cfg),  # o simulado não toca no git
    }
    relatorio = harness.run_ab(chamadas, runner, escolhidos, len(tarefas), metodo)
    pasta.mkdir(parents=True, exist_ok=True)
    dados = json.dumps(relatorio.to_json(), ensure_ascii=False, indent=1)
    (pasta / f"{time.strftime('%Y%m%d-%H%M%S')}{'-simulado' if simulate else ''}.json").write_text(dados, encoding="utf-8")
    (pasta / "latest.json").write_text(dados, encoding="utf-8")

    if as_json:
        console.print_json(dados)
        return
    _resumo(relatorio)


def _guardas(chamadas: list[Any], max_calls: int | None) -> None:
    """`--execute` gasta cota da conta: recusa sem as duas guardas, e diz o que seria gasto."""
    plano = f"{len(chamadas)} chamadas reais a `claude -p` (cada uma consome a cota da sua conta)"
    if os.environ.get("RAGX_AB_REAL") != "1":
        raise UsageError(f"--execute recusado: {plano}. Para confirmar, defina RAGX_AB_REAL=1.")
    if max_calls is None:
        raise UsageError(f"--execute recusado: {plano}. Informe o teto com --max-calls N.")
    if len(chamadas) > max_calls:
        raise UsageError(
            f"--execute recusado: o plano tem {len(chamadas)} chamadas e --max-calls é {max_calls}. "
            "Reduza --limit, --reps ou --arms, ou aumente o teto."
        )
    if shutil.which("claude") is None:
        raise UsageError("`claude` não está no PATH")


def _commit(cfg: Any) -> str | None:
    try:
        from ragx import gitinfo

        estado = gitinfo.read_state(cfg.root)
        return estado.commit if estado else None
    except Exception:
        return None


def _plano(chamadas: list[Any], arms: list[str], tarefas: list[Any], reps: int, as_json: bool) -> None:
    por_braco = {a: sum(1 for c in chamadas if c.arm == a) for a in arms}
    if as_json:
        console.print_json(json.dumps({
            "dry_run": True, "calls": len(chamadas), "tasks": len(tarefas), "reps": reps,
            "by_arm": por_braco,
            "planned": [{"arm": c.arm, "task": c.task_index, "rep": c.rep, "argv": list(c.argv)} for c in chamadas],
        }, ensure_ascii=False))
        return
    console.print(f"\n[bold]Plano do A/B[/] (nada foi executado): {len(tarefas)} tarefas × {len(arms)} braços × {reps} repetição(ões)")
    for a, n in por_braco.items():
        console.print(f"  [cyan]{a:<8}[/] {n} chamada(s)")
    console.print(f"\n  Total: [bold]{len(chamadas)}[/] chamadas a `claude -p`.")
    exemplo = chamadas[0]
    console.print(f"  Primeira chamada (o prompt vai pelo stdin): [dim]{' '.join(exemplo.argv)}[/]")
    console.print(
        "\n  [yellow]Para rodar de verdade[/] (gasta cota da sua conta):\n"
        f"    RAGX_AB_REAL=1 ragx ab --execute --max-calls {len(chamadas)}"
        + (f" --model {chamadas[0].argv[chamadas[0].argv.index('--model') + 1]}" if "--model" in chamadas[0].argv else "")
        + "\n  Para testar o harness sem custo: ragx ab --simulate\n"
    )


def _resumo(relatorio: Any) -> None:
    sim = relatorio.simulated
    if sim:
        console.print("\n[bold red]SIMULADO[/] — os números abaixo são SINTÉTICOS, não são economia real.\n")
    else:
        console.print("\n[bold]Resultado do A/B[/]\n")
    for arm, d in relatorio.summary["arms"].items():
        console.print(
            f"  [cyan]{arm:<8}[/] acertos {d['hit_rate']}  tokens faturáveis (mediana) {d['billable_tokens_median']}  "
            f"custo (mediana) {d['cost_usd_median']}  erros {d['errors']}"
        )
    for nome, c in relatorio.summary["comparisons"].items():
        rotulo = "" if not sim else " (simulado)"
        console.print(
            f"  {nome}: economia mediana {100 * c['saving_median']:+.1f}% "
            f"[IC95% {100 * c['ci95'][0]:+.1f}% a {100 * c['ci95'][1]:+.1f}%] em {c['pairs']} pares — "
            f"[bold]{c['label']}[/]{rotulo}"
        )
    console.print()

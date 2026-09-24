"""`ragx perf` — quanto tempo das sessões do Claude Code o RAGX ocupa."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def _fmt(ms: float) -> str:
    return f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms:.0f}ms"


def _footprint() -> tuple[int, int] | None:
    """Ferramentas e tokens estimados que o RAGX põe em TODA requisição ao modelo."""
    try:
        import asyncio

        from ragx.config import load_config
        from ragx.mcp.server import build_server

        listed = asyncio.run(build_server(load_config(), allow_write=True).list_tools())
        chars = sum(
            len(json.dumps({"n": t.name, "d": t.description, "s": getattr(t, "inputSchema", None)},
                           ensure_ascii=False, default=str))
            for t in listed
        )
        return len(listed), chars // 4
    except Exception:
        return None


def perf(
    days: Annotated[int, typer.Option("--days", help="Janela de análise, em dias.")] = 7,
    project: Annotated[
        str | None, typer.Option("--project", help="Filtra por trecho do nome da pasta do projeto.")
    ] = None,
    top: Annotated[int, typer.Option("--top", help="Quantas sessões listar.")] = 5,
    directory: Annotated[
        Path | None,
        typer.Option("--dir", help="Pasta de transcripts (padrão: ~/.claude/projects)."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mede o peso do RAGX nas suas sessões do Claude Code.

    Lê os transcripts do Claude Code, que carimbam cada mensagem, e separa o tempo
    das voltas do modelo e das ferramentas que foram do RAGX. É estimativa, e erra
    para menos. Compare com o servidor: ele responde em milissegundos, o custo
    está nas voltas extras.
    """
    from ragx import perf as p
    from ragx.config import find_root

    root = directory or Path.home() / ".claude" / "projects"
    since = datetime.now(UTC) - timedelta(days=days)
    sessions = p.load_sessions(root, since=since, project=project)
    with_ragx = [s for s in sessions if s.calls]

    active = sum(s.active_ms for s in with_ragx)
    overhead = sum(s.overhead_ms for s in with_ragx)
    calls = sum(s.calls for s in with_ragx)
    wall = p.tool_wall_stats(with_ragx)
    try:
        state_dir = find_root(Path.cwd())[0] / ".ragx"
    except Exception:
        state_dir = Path.cwd() / ".ragx"
    server = p.server_stats(state_dir / "logs" / "mcp.jsonl")

    summary = {
        "days": days,
        "sessions": len(sessions),
        "sessions_with_ragx": len(with_ragx),
        "calls": calls,
        "overhead_ms": overhead,
        "active_ms": active,
        "share": round(overhead / active, 4) if active else 0.0,
    }
    tools = [
        {
            "tool": t,
            "n": s.n,
            "wall_p50_ms": s.p50,
            "wall_p95_ms": s.p95,
            "server_p50_ms": server[t.removeprefix(p.RAGX_PREFIX)].p50
            if t.removeprefix(p.RAGX_PREFIX) in server
            else None,
        }
        for t, s in sorted(wall.items(), key=lambda kv: -kv[1].n)
    ]

    if as_json:
        console.print_json(json.dumps({"summary": summary, "tools": tools}, ensure_ascii=False))
        return

    console.print(f"\n[bold]RAGX nas sessões do Claude Code[/] — últimos {days} dias\n")
    if not with_ragx:
        console.print(
            f"  {len(sessions)} sessão(ões) analisada(s), nenhuma chamou o RAGX. "
            "[dim]Sem o que medir.[/]\n"
        )
        return
    console.print(
        f"  {len(with_ragx)} de {len(sessions)} sessões usaram o RAGX · {calls} chamadas\n"
        f"  Tempo ativo nessas sessões (sem contar você): [bold]{_fmt(active)}[/]\n"
        f"  Tempo em voltas do RAGX (modelo + ferramenta): [bold]{_fmt(overhead)}[/] "
        f"= [bold]{summary['share'] * 100:.1f}%[/]\n"
    )

    table = Table(title="Por ferramenta", title_justify="left")
    for col in ("ferramenta", "chamadas", "espera p50", "espera p95", "servidor p50"):
        table.add_column(col, justify="left" if col == "ferramenta" else "right")
    for row in tools:
        table.add_row(
            row["tool"].removeprefix(p.RAGX_PREFIX),
            str(row["n"]),
            _fmt(row["wall_p50_ms"]),
            _fmt(row["wall_p95_ms"]),
            _fmt(row["server_p50_ms"]) if row["server_p50_ms"] is not None else "—",
        )
    console.print(table)
    console.print(
        "  [dim]espera = do pedido do modelo ao resultado; servidor = só o processamento do "
        "RAGX (este projeto). A diferença é transporte do Claude Code.[/]\n"
    )

    worst = sorted(with_ragx, key=lambda s: -s.overhead_ms)[:top]
    sess = Table(title=f"Sessões com mais tempo no RAGX (top {len(worst)})", title_justify="left")
    for col in ("projeto", "início", "chamadas", "no RAGX", "de", "%"):
        sess.add_column(col, justify="left" if col in ("projeto", "início") else "right")
    for s in worst:
        sess.add_row(
            s.project.split("-")[-1] or s.project,
            s.started.astimezone().strftime("%d/%m %H:%M") if s.started else "—",
            str(s.calls),
            _fmt(s.overhead_ms),
            _fmt(s.active_ms),
            f"{s.share * 100:.0f}%",
        )
    console.print(sess)

    fp = _footprint()
    if fp:
        console.print(
            f"\n  Fixo em toda requisição: {fp[0]} ferramentas ≈ {fp[1]} tokens de schema. "
            "[dim]Desligue com `ragx claude off`.[/]\n"
        )

"""`ragx watch` — mantém o índice acompanhando o working tree."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from ragx.config import load_config
from ragx.watch.monitor import Delta, WatchState
from ragx.watch.monitor import watch as run_watch

console = Console()

_MAX_LINHAS = 8


def watch(
    interval: Annotated[float, typer.Option("--interval", help="Segundos entre varreduras.")] = 0.0,
    debounce: Annotated[float, typer.Option("--debounce", help="Quietude antes de reindexar.")] = 0.0,
    consolidate_every: Annotated[
        int, typer.Option("--consolidate-every", help="Mudanças até regravar knowledge/.")
    ] = 0,
    once: Annotated[bool, typer.Option("--once", help="Uma varredura e sai (para scripts/CI).")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="Uma linha por evento, sem painel.")] = False,
) -> None:
    """Observa mudanças e reindexa sozinho.

    Duas velocidades: cada alteração reindexa (barato), e a cada N alterações o
    grafo, o dicionário e o `knowledge/` versionado são regravados.

    Ctrl+C encerra.
    """
    cfg = load_config()
    if interval > 0:
        cfg.watch.interval_s = interval
    if debounce > 0:
        cfg.watch.debounce_s = debounce
    if consolidate_every > 0:
        cfg.watch.full_sync_every = consolidate_every

    if not cfg.db_path.exists():
        console.print("\n[yellow]sem índice.[/] Rode: [bold]ragx init && ragx index .[/]\n")
        raise typer.Exit(1)

    if once:
        _once(cfg, plain)
        return

    console.print(
        f"\n[bold]ragx watch[/]  [dim]{cfg.root}[/]"
        f"\n  [dim]varredura a cada {cfg.watch.interval_s:g}s · "
        f"debounce {cfg.watch.debounce_s:g}s · "
        f"consolida a cada {cfg.watch.full_sync_every} mudanças[/]"
        "\n  [dim]Ctrl+C para sair[/]\n"
    )

    recentes: list[str] = []

    if plain:
        def on_event(kind: str, d: Delta, st: WatchState) -> None:
            if kind == "change":
                for p in d.paths[:_MAX_LINHAS]:
                    console.print(f"  [dim]~[/] {p}")
            elif kind == "apply":
                _print_apply(d, st)

        try:
            run_watch(cfg, on_event=on_event)
        except KeyboardInterrupt:
            _bye(None)
        return

    with Live(_panel(recentes, WatchState()), console=console, refresh_per_second=4) as live:
        def on_event(kind: str, d: Delta, st: WatchState) -> None:
            if kind == "change":
                for p in d.paths[:_MAX_LINHAS]:
                    recentes.append(f"~ {p}")
            elif kind == "apply":
                recentes.append(
                    f"✓ {d.total} arquivo(s) reindexado(s)"
                    + ("  · consolidado" if st.since_consolidation == 0 else "")
                )
            del recentes[:-_MAX_LINHAS]
            live.update(_panel(recentes, st))

        try:
            st = run_watch(cfg, on_event=on_event)
        except KeyboardInterrupt:
            _bye(None)
            return
    _bye(st)


def _once(cfg: object, plain: bool) -> None:
    """Uma varredura: aplica o que estiver pendente e sai."""
    from ragx.watch.monitor import WatchState, apply_changes

    st = WatchState()
    apply_changes(cfg, st, consolidate=True)  # type: ignore[arg-type]
    if plain:
        console.print_json(json.dumps({
            "indexed": st.indexed, "blocked": st.blocked,
            "consolidations": st.consolidations, "error": st.last_error,
            "warnings": st.warnings,
        }, ensure_ascii=False))
        return
    console.print(
        f"\n[green]✓[/] {st.indexed} documento(s) reindexado(s)"
        + (f", [yellow]{st.blocked} bloqueado(s)[/]" if st.blocked else "")
    )
    if st.last_error:
        console.print(f"  [red]{st.last_error}[/]")
    console.print()


def _print_apply(d: Delta, st: WatchState) -> None:
    extra = "  [dim]· consolidado[/]" if st.since_consolidation == 0 else ""
    console.print(f"  [green]✓[/] {d.total} arquivo(s) reindexado(s){extra}")
    if st.last_error:
        console.print(f"  [red]![/] {st.last_error}")


def _panel(recentes: list[str], st: WatchState) -> Table:
    t = Table(box=None, pad_edge=False, show_header=False)
    t.add_column(overflow="fold")
    for linha in recentes or ["[dim]aguardando mudanças…[/]"]:
        cor = "green" if linha.startswith("✓") else "dim"
        t.add_row(f"[{cor}]{linha}[/]")
    t.add_row("")
    t.add_row(
        f"[dim]ciclos {st.cycles} · reindexações {st.applied} · "
        f"consolidações {st.consolidations} · documentos {st.indexed}"
        + (f" · [yellow]bloqueados {st.blocked}[/]" if st.blocked else "")
        + "[/]"
    )
    if st.last_error:
        t.add_row(f"[red]{st.last_error}[/]")
    return t


def _bye(st: WatchState | None) -> None:
    if st is None:
        console.print("\n[dim]watch encerrado.[/]\n")
        return
    console.print(
        f"\n[dim]watch encerrado — {st.applied} reindexações, "
        f"{st.consolidations} consolidações.[/]\n"
    )

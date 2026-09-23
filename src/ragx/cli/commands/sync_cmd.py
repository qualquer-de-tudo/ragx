"""`ragx sync`."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config

console = Console()


def sync(
    from_commit: Annotated[str | None, typer.Option("--from-commit")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    resolve: Annotated[bool, typer.Option("--resolve", help="Rederiva artefatos em conflito.")] = False,
    resolve_file: Annotated[str | None, typer.Option("--resolve-file")] = None,
    quiet: Annotated[bool, typer.Option("--quiet")] = False,
    report: Annotated[bool, typer.Option("--report", help="Detalha a reidratação.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Reconstrói o índice a partir de knowledge/ + working tree."""
    from ragx.core.errors import IndexBusyError
    from ragx.sync.service import resolve as run_resolve
    from ragx.sync.service import sync as run_sync

    cfg = load_config()
    try:
        if resolve or resolve_file:
            r = run_resolve(cfg, resolve_file)
        else:
            r = run_sync(cfg, from_commit=from_commit, full=full)
    except IndexBusyError as exc:
        # A mensagem GENÉRICA de IndexBusyError ("este pedido ficou agendado")
        # não vale pra `sync`: a trava (.ragx/index.lock) só cobre
        # `index_project`, e o que reroda sozinho quando ela libera é SÓ a
        # reindexação incremental — knowledge/, grafo, dicionário e federação
        # não são reagendados. Sem esta correção quem lê "agendado" concluía
        # que o sync inteiro ia terminar de rodar sozinho; não vai.
        who = exc.holder.get("source", "outra origem")
        pid = exc.holder.get("pid", "?")
        msg = (
            f"outra indexação está rodando (origem {who}, pid {pid}). "
            "Só a reindexação deste `sync` fica agendada e roda quando ela "
            "terminar — knowledge/, grafo, dicionário e federação NÃO são "
            "refeitos automaticamente; rode `ragx sync` de novo depois."
        )
        if as_json:
            console.print_json(json.dumps(
                {"ok": False, "error": {"code": "busy", "message": msg}},
                ensure_ascii=False,
            ))
        elif not quiet:
            Console(stderr=True).print(f"[yellow]{msg}[/]")
        raise typer.Exit(code=exc.exit_code) from exc

    if as_json:
        console.print_json(json.dumps({
            "mode": r.mode, "from": r.from_commit, "to": r.to_commit,
            "changed_files": len(r.changed),
            "rehydrate": {
                "total": r.rehydrate.total, "ok": r.rehydrate.ok,
                "hash_mismatch": r.rehydrate.mismatch,
                "file_missing": r.rehydrate.missing,
                "blocked": r.rehydrate.blocked,
                "synthetic": r.rehydrate.synthetic,
            },
            "indexed": r.indexed, "unchanged": r.unchanged, "removed": r.removed,
            "chunks": r.chunks, "embedded": r.embedded,
            "entities": r.entities, "relations": r.relations,
            "knowledge_bytes": r.serialized.bytes_written if r.serialized else 0,
            "warnings": r.warnings, "duration_ms": r.duration_ms,
        }, ensure_ascii=False))
        return
    if quiet:
        return

    console.print(f"\n[bold]Sync[/] — {cfg.root}\n")
    if r.mode == "git" and r.from_commit:
        console.print(f"  Git:         {r.from_commit[:7]} → {(r.to_commit or '')[:7]}"
                      f"  ({len(r.changed)} arquivo(s) no diff)")
    else:
        console.print("  [dim]Delta por content_hash (sem Git ou commit ausente)[/]")

    h = r.rehydrate
    if h.total:
        console.print(
            f"\n  Reidratação: {h.total} chunks · [green]{h.ok} ok[/]"
            + (f" · [yellow]{h.mismatch} re-derivados[/]" if h.mismatch else "")
            + (f" · [red]{h.missing} descartados[/]" if h.missing else "")
        )
    console.print(
        f"\n  Indexados    {r.indexed:>6}   Unchanged {r.unchanged:>6}   "
        f"Removidos {r.removed:>4}"
    )
    console.print(f"  Chunks       {r.chunks:>6}   Embeddings {r.embedded:>5}")
    if r.entities:
        console.print(f"  Entidades    {r.entities:>6}   Relações   {r.relations:>5}")
    if r.serialized:
        s = r.serialized
        kb = s.bytes_written / 1024
        console.print(
            f"  knowledge/   {s.files_written:>6} arquivos, {kb:.0f} KB"
            + (f"  [dim]({s.removed} obsoletos removidos)[/]" if s.removed else "")
        )
    for w in r.warnings:
        console.print(f"  [yellow]! {w}[/]")
    if report and h.dropped:
        console.print("\n  [dim]descartados:[/]")
        for cid, why in h.dropped[:15]:
            console.print(f"    [dim]{cid[:12]}  {why}[/]")
    console.print(f"\n  Tempo {r.duration_ms / 1000:.1f} s\n")

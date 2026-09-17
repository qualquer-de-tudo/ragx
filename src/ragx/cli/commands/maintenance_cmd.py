"""`ragx vacuum`, `ragx reset` — manutenção e recuperação (Fase 10)."""

from __future__ import annotations

import json
import shutil
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config

console = Console()

# Órfãos possíveis, na ordem em que precisam ser removidos.
_ORPHAN_QUERIES = (
    ("embeddings sem chunk",
     "DELETE FROM embeddings WHERE chunk_id NOT IN (SELECT id FROM chunks)"),
    ("embeddings de modelo removido",
     "DELETE FROM embeddings WHERE model_id NOT IN (SELECT id FROM embedding_models)"),
    ("chunks sem documento",
     "DELETE FROM chunks WHERE document_id NOT IN (SELECT id FROM documents)"),
    ("entidades sem documento",
     "DELETE FROM entities WHERE document_id IS NOT NULL "
     "AND document_id NOT IN (SELECT id FROM documents)"),
    ("relações sem entidade",
     "DELETE FROM relations WHERE src_id NOT IN (SELECT id FROM entities) "
     "OR dst_id NOT IN (SELECT id FROM entities)"),
    ("eventos de runs inexistentes",
     "DELETE FROM security_events WHERE run_id IS NOT NULL "
     "AND run_id NOT IN (SELECT id FROM index_runs)"),
)


def vacuum(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Remove órfãos, compacta o banco e otimiza os índices."""
    from ragx.storage.db import open_db

    cfg = load_config()
    if not cfg.db_path.exists():
        console.print("\n[yellow]sem banco.[/] Rode: [bold]ragx init[/]\n")
        raise typer.Exit(1)

    antes = cfg.db_path.stat().st_size
    removed: dict[str, int] = {}
    with open_db(cfg.db_path) as conn:
        for label, sql in _ORPHAN_QUERIES:
            cur = conn.execute(sql)
            if cur.rowcount and cur.rowcount > 0:
                removed[label] = cur.rowcount
        conn.commit()
        conn.execute("PRAGMA optimize")
        conn.execute("VACUUM")
    depois = cfg.db_path.stat().st_size

    if as_json:
        console.print_json(json.dumps({
            "removed": removed, "bytes_before": antes, "bytes_after": depois,
            "reclaimed": antes - depois,
        }, ensure_ascii=False))
        return

    console.print("\n[bold]Vacuum[/]\n")
    for label, n in removed.items():
        console.print(f"  [yellow]{n:>6}[/] {label}")
    if not removed:
        console.print("  [dim]nenhum órfão[/]")
    delta = (antes - depois) / 1024
    console.print(
        f"\n  {antes / 1024 / 1024:.1f} MB → {depois / 1024 / 1024:.1f} MB"
        + (f"  [green](-{delta:.0f} KB)[/]" if delta > 0 else "")
    )
    console.print()


def reset(
    hard: Annotated[bool, typer.Option("--hard", help="Também apaga knowledge/.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Não perguntar.")] = False,
) -> None:
    """Apaga o índice local. Tudo é reconstruível."""
    cfg = load_config()
    alvos = [cfg.state_dir]
    if hard:
        alvos.append(cfg.knowledge_dir)

    existentes = [p for p in alvos if p.exists()]
    if not existentes:
        console.print("\n[dim]nada a apagar[/]\n")
        return

    console.print("\n[bold]Será apagado:[/]")
    for p in existentes:
        n = sum(1 for _ in p.rglob("*"))
        console.print(f"  {p}  [dim]({n} entradas)[/]")
    if hard:
        console.print(
            "\n  [yellow]--hard apaga knowledge/, que é VERSIONADO.[/]"
            "\n  [dim]Reconstruível com `ragx index . && ragx sync`.[/]"
        )
    else:
        console.print("\n  [dim].ragx/ é derivado; `ragx sync` reconstrói.[/]")

    if not yes and not typer.confirm("\nConfirmar?"):
        raise typer.Exit(1)

    for p in existentes:
        shutil.rmtree(p, ignore_errors=True)
    console.print("\n[green]✓[/] apagado. Rode [bold]ragx sync[/] para reconstruir.\n")


def integrity(cfg_path: str | None = None) -> str:
    from ragx.storage.db import integrity_check, open_db

    cfg = load_config(cfg_path)
    with open_db(cfg.db_path, read_only=True) as conn:
        return integrity_check(conn)

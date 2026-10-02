"""`ragx worktree status` (RAGX-0170)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command("status")
def status(
    path: Annotated[Path, typer.Argument()] = Path("."),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Worktrees do repositório, o tamanho de cada índice e quantos chunks compartilham com este."""
    from ragx import worktrees

    cfg = load_config(path.resolve())
    rel = worktrees.report(cfg)
    if as_json:
        console.print_json(json.dumps(rel, ensure_ascii=False))
        return
    itens = rel["worktrees"]
    if not itens:
        console.print("\n[dim]Fora de um repositório git (ou sem worktrees).[/]\n")
        return
    console.print()
    for w in itens:
        marca = "[green]*[/]" if w["current"] else " "
        ramo = w["branch"] or ("(detached)" if w["detached"] else "-")
        if not w["indexed"]:
            console.print(f" {marca} {w['path']}  [{ramo}]  [dim]sem índice[/]")
            continue
        comum = "" if w["current"] else f", {w.get('shared_chunks', 0):,} em comum com este"
        console.print(f" {marca} {w['path']}  [{ramo}]  {w['documents']:,} docs, {w['chunks']:,} chunks{comum}")
    cache = rel["embedding_cache"]
    onde = "compartilhado entre os worktrees" if cache["shared"] else "local deste projeto"
    console.print(f"\n  Cache de embedding ({onde}): {cache['size_mb']} MB em {cache['path']}\n")

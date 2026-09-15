"""`ragx export`, `ragx import`, `ragx inspect`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError
from ragx.portability import importer, package

console = Console()


def export(
    target: Annotated[Path, typer.Argument(help="Arquivo .rag de saída.")],
    include_embeddings: Annotated[bool, typer.Option("--include-embeddings/--no-embeddings")] = True,
    include_agents: Annotated[bool, typer.Option("--include-agents")] = False,
    full_vectors: Annotated[bool, typer.Option("--full-vectors", help="float32: 12x maior.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Empacota o conhecimento em um arquivo .rag."""
    cfg = load_config()
    r = package.export(cfg, target, include_embeddings, include_agents, full_vectors)
    if as_json:
        console.print_json(json.dumps({
            "path": r.path, "bytes": r.bytes_written, "counts": r.counts,
            "findings": len(r.findings), "embeddings": r.included_embeddings,
        }, ensure_ascii=False))
        return
    console.print(f"\n[bold green]Exportado[/] — {r.path}\n")
    for k, v in r.counts.items():
        console.print(f"  [cyan]{k:<13}[/] {v:>7,}")
    console.print(f"\n  {r.bytes_written / 1024:.0f} KB")
    if r.findings:
        console.print(f"  [yellow]{len(r.findings)} achado(s) não bloqueante(s)[/]")
    console.print()


def import_(
    source: Annotated[Path, typer.Argument(help="Arquivo .rag de entrada.")],
    replace: Annotated[bool, typer.Option("--replace/--merge")] = True,
    skip_embeddings: Annotated[bool, typer.Option("--skip-embeddings")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Importa conhecimento de um arquivo .rag."""
    if not source.is_file():
        raise UsageError(f"pacote não encontrado: {source}")
    cfg = load_config()
    r = importer.import_package(
        cfg, source, mode="replace" if replace else "merge", skip_embeddings=skip_embeddings
    )
    if as_json:
        console.print_json(json.dumps({
            "source": r.source, "mode": r.mode, "applied": r.applied,
            "skipped": r.skipped, "warnings": r.warnings,
        }, ensure_ascii=False))
        return
    console.print(f"\n[bold green]Importado[/] — {r.source}  [dim]({r.mode})[/]\n")
    for k, v in r.applied.items():
        console.print(f"  [cyan]{k:<13}[/] {v:>7,}")
    for k, why in r.skipped.items():
        console.print(f"  [yellow]{k:<13} ignorado: {why}[/]")
    for w in r.warnings:
        console.print(f"  [yellow]! {w}[/]")
    console.print()


def inspect(
    source: Annotated[Path, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lê o manifest de um .rag sem descompactar o pacote."""
    if not source.is_file():
        raise UsageError(f"pacote não encontrado: {source}")
    manifest = package.inspect(source)
    if as_json:
        console.print_json(json.dumps(manifest, ensure_ascii=False))
        return
    console.print(f"\n[bold]{source.name}[/]\n")
    console.print(f"  Projeto      {manifest['project']['name']}  [dim]{manifest['project']['project_id']}[/]")
    console.print(f"  Criado em    {manifest['created_at']}")
    console.print("\n  [bold]Conteúdo[/]")
    for k, v in manifest["contents"].items():
        console.print(f"    {k:<13} {v:>7,}")
    console.print("\n  [bold]Versões[/]")
    for k, v in manifest["versions"].items():
        console.print(f"    {k:<17} {v}")
    sec = manifest.get("security", {})
    console.print(f"\n  Segurança    política={sec.get('policy')} · achados={sec.get('findings', 0)}")
    console.print()

"""`ragx dictionary generate|show`."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command("generate")
def generate(
    semantic: Annotated[bool, typer.Option("--semantic", help="Enriquece com LLM (opt-in).")] = False,
    out: Annotated[str | None, typer.Option("--out")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Gera knowledge/dictionary.json."""
    from ragx.dictionary import builder

    cfg = load_config()
    if semantic:
        console.print(
            "[yellow]![/] enriquecimento semântico ainda não implementado "
            "(RAGX-0044); gerando só as seções determinísticas."
        )
    data, report = builder.build(cfg, semantic=False)
    written = builder.write(cfg, data, out)

    if as_json:
        console.print_json(json.dumps({
            "path": written.path, "bytes": written.bytes_written,
            "sections": report.sections, "redacted_items": report.redacted_items,
            "digest": builder.stable_digest(data),
        }, ensure_ascii=False))
        return

    console.print(f"\n[bold green]Dicionário gerado[/] — {written.path}\n")
    for name, n in sorted(report.sections.items(), key=lambda kv: -kv[1]):
        if n:
            console.print(f"  [cyan]{name:<15}[/] {n:>5}")
    kb = written.bytes_written / 1024
    console.print(f"\n  {kb:.1f} KB  [dim]digest {builder.stable_digest(data)}[/]")
    if report.redacted_items:
        console.print(f"  [yellow]{report.redacted_items} item(ns) redigido(s) pelo re-scan[/]")
    console.print()


@app.command("show")
def show(
    section: Annotated[str | None, typer.Option("--section")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mostra o dicionário (ou uma seção)."""
    from ragx.dictionary import builder

    cfg = load_config()
    data = builder.load(cfg)
    if data is None:
        console.print("\n[yellow]dicionário ausente.[/] Rode: [bold]ragx dictionary generate[/]\n")
        raise typer.Exit(1)

    if section:
        if section not in data:
            raise UsageError(
                f"seção desconhecida: {section!r} (disponíveis: {', '.join(sorted(data))})"
            )
        data = {section: data[section]}

    if as_json:
        console.print_json(json.dumps(data, ensure_ascii=False))
        return

    for name, value in data.items():
        if name in ("schema_version",) or not value:
            continue
        console.print(f"\n[bold cyan]{name}[/]")
        if isinstance(value, dict):
            for k, v in list(value.items())[:20]:
                console.print(f"  {k}: [dim]{', '.join(v) if isinstance(v, list) else v}[/]")
        elif isinstance(value, list):
            for item in value[:20]:
                if isinstance(item, dict):
                    head = item.get("name") or item.get("rule") or item.get("value") or item.get("path") or item.get("term")
                    extra = item.get("path") or item.get("evidence") or ""
                    console.print(f"  {head}  [dim]{extra}[/]")
                else:
                    console.print(f"  {item}")
    console.print()

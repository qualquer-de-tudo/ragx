"""`ragx mcp serve|tools`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command("serve")
def serve(
    project: Annotated[Path | None, typer.Option("--project")] = None,
    transport: Annotated[str, typer.Option("--transport")] = "stdio",
    allow_index: Annotated[bool, typer.Option("--allow-index")] = False,
    write: Annotated[
        bool,
        typer.Option(
            "--write/--read-only",
            help="Deixa o agente reindexar e sincronizar. Não afeta o Security Gate.",
        ),
    ] = True,
) -> None:
    """Sobe o servidor MCP (stdio).

    Escrita vem LIGADA: o agente controla o índice (reindex, sync, grafo,
    dicionário). O que ele continua sem poder é ler o filesystem ou escapar do
    Security Gate — `--read-only` remove só as operações de escrita.
    """
    from ragx.mcp.server import serve as run

    run(
        project=str(project) if project else None,
        allow_index=allow_index,
        allow_write=write,
    )


@app.command("tools")
def tools(
    as_json: Annotated[bool, typer.Option("--json")] = False,
    write: Annotated[bool, typer.Option("--write/--read-only")] = True,
) -> None:
    """Lista as ferramentas expostas e seus schemas."""
    import asyncio

    from ragx.mcp.server import build_server

    server = build_server(load_config(), allow_write=write)
    listed = asyncio.run(server.list_tools())
    payload = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": getattr(t, "inputSchema", None) or getattr(t, "parameters", None),
        }
        for t in listed
    ]
    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
        return
    console.print(f"\n[bold]Ferramentas MCP[/] — {len(payload)}\n")
    for t in payload:
        console.print(f"  [cyan]{t['name']}[/]")
        console.print(f"    [dim]{t['description']}[/]")
    console.print()

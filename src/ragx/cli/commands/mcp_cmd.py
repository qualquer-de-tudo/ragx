"""`ragx mcp serve|tools`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

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


@app.command("install")
def install(
    client: Annotated[
        list[str] | None,
        typer.Option(
            "--client",
            help="Registrar só nestes clientes (repetível): "
            "claude-desktop, claude-code, cursor, windsurf, gemini, codex.",
        ),
    ] = None,
    command: Annotated[
        str, typer.Option("--command", help="Executável do RAGX gravado na configuração.")
    ] = "ragx",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Mostra o que mudaria, sem escrever nada.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Registra o RAGX como servidor MCP nos clientes instalados.

    Idempotente: rodar de novo não duplica entrada nem reescreve o que já está
    certo. A configuração existente é preservada — só a entrada `ragx` é
    tocada, e há backup datado antes de qualquer mudança.
    """
    from ragx.clients import Outcome, register_all

    resultados = register_all(command=command, dry_run=dry_run, only=client)

    if as_json:
        console.print_json(
            json.dumps(
                [
                    {
                        "client": r.client.id,
                        "label": r.client.label,
                        "config": str(r.client.config),
                        "outcome": r.outcome.value,
                        "detail": r.detail,
                        "backup": str(r.backup) if r.backup else None,
                    }
                    for r in resultados
                ],
                ensure_ascii=False,
            )
        )
        raise typer.Exit(0 if all(r.ok for r in resultados) else 1)

    icones = {
        Outcome.CREATED: "[green]+[/]",
        Outcome.UPDATED: "[green]~[/]",
        Outcome.UNCHANGED: "[dim]=[/]",
        Outcome.ABSENT: "[dim]·[/]",
        Outcome.REMOVED: "[green]-[/]",
        Outcome.FAILED: "[red]x[/]",
    }
    console.print(f"\n[bold]Registro do servidor MCP[/]{'  [yellow](simulação)[/]' if dry_run else ''}\n")
    # `escape`: as mensagens carregam coisas como `[mcp_servers.ragx]`, e o Rich
    # leria isso como marcação e apagaria o texto — o resultado era a linha
    # "tabela `` registrada", sem dizer QUAL tabela.
    for r in resultados:
        console.print(f"  {icones[r.outcome]} [cyan]{r.client.label:<16}[/] {escape(r.detail)}")
        if r.outcome in (Outcome.CREATED, Outcome.UPDATED, Outcome.FAILED):
            console.print(f"      [dim]{escape(str(r.client.config))}[/]")
        if r.backup:
            console.print(f"      [dim]backup: {r.backup.name}[/]")

    mudou = [r for r in resultados if r.outcome in (Outcome.CREATED, Outcome.UPDATED)]
    falhou = [r for r in resultados if r.outcome is Outcome.FAILED]
    ausentes = [r for r in resultados if r.outcome is Outcome.ABSENT]

    console.print(
        f"\n  {len(mudou)} alterado(s) · "
        f"{len(resultados) - len(mudou) - len(falhou) - len(ausentes)} já em dia · "
        f"{len(ausentes)} não instalado(s) · {len(falhou)} com falha\n"
    )
    if mudou and not dry_run:
        console.print("  [dim]Reinicie o cliente para que ele leia a configuração nova.[/]\n")
    raise typer.Exit(1 if falhou else 0)


@app.command("uninstall")
def uninstall(
    client: Annotated[
        list[str] | None,
        typer.Option(
            "--client",
            help="Remover só destes clientes (repetível): "
            "claude-desktop, claude-code, cursor, windsurf, gemini, codex.",
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Mostra o que mudaria, sem escrever nada.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Remove o RAGX da configuração MCP dos clientes.

    Idempotente e conservador como o `install`: só a entrada `ragx` é retirada,
    o resto da configuração fica intacto, e há backup datado antes de mudar.
    """
    from ragx.clients import Outcome, unregister_all

    resultados = unregister_all(dry_run=dry_run, only=client)

    if as_json:
        console.print_json(
            json.dumps(
                [
                    {
                        "client": r.client.id,
                        "label": r.client.label,
                        "config": str(r.client.config),
                        "outcome": r.outcome.value,
                        "detail": r.detail,
                        "backup": str(r.backup) if r.backup else None,
                    }
                    for r in resultados
                ],
                ensure_ascii=False,
            )
        )
        raise typer.Exit(0 if all(r.ok for r in resultados) else 1)

    icones = {
        Outcome.REMOVED: "[green]-[/]",
        Outcome.UNCHANGED: "[dim]=[/]",
        Outcome.ABSENT: "[dim]·[/]",
        Outcome.FAILED: "[red]x[/]",
        Outcome.CREATED: "[green]+[/]",
        Outcome.UPDATED: "[green]~[/]",
    }
    console.print(
        f"\n[bold]Remoção do servidor MCP[/]{'  [yellow](simulação)[/]' if dry_run else ''}\n"
    )
    for r in resultados:
        console.print(f"  {icones[r.outcome]} [cyan]{r.client.label:<16}[/] {escape(r.detail)}")
        if r.outcome in (Outcome.REMOVED, Outcome.FAILED):
            console.print(f"      [dim]{escape(str(r.client.config))}[/]")
        if r.backup:
            console.print(f"      [dim]backup: {r.backup.name}[/]")

    removidos = [r for r in resultados if r.outcome is Outcome.REMOVED]
    falhou = [r for r in resultados if r.outcome is Outcome.FAILED]
    ausentes = [r for r in resultados if r.outcome is Outcome.ABSENT]
    console.print(
        f"\n  {len(removidos)} removido(s) · "
        f"{len(resultados) - len(removidos) - len(falhou) - len(ausentes)} já sem o RAGX · "
        f"{len(ausentes)} não instalado(s) · {len(falhou)} com falha\n"
    )
    if removidos and not dry_run:
        console.print("  [dim]Reinicie o cliente para que ele leia a configuração nova.[/]\n")
    raise typer.Exit(1 if falhou else 0)

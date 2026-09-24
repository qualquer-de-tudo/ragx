"""`ragx claude on|off|status` — liga e desliga o RAGX no Claude Code, para todos os projetos."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
app = typer.Typer(no_args_is_help=True)

_CLIENT = "claude-code"


def _client():
    from ragx.clients import CLIENTS

    return next(c for c in CLIENTS() if c.id == _CLIENT)


def _report(results, verbo: str, as_json: bool) -> None:
    from ragx.clients import is_registered

    r = results[0]
    if as_json:
        payload = {
            "enabled": is_registered(_client()),
            "changed": r.outcome.value in ("created", "updated", "removed"),
            "detail": r.detail,
        }
        if not r.ok:
            payload["error"] = r.detail
        console.print_json(json.dumps(payload, ensure_ascii=False))
        raise typer.Exit(0 if r.ok else 1)
    console.print(f"\n  [cyan]Claude Code[/] {escape(r.detail)}")
    if r.backup:
        console.print(f"      [dim]backup: {r.backup.name}[/]")
    if not r.ok:
        raise typer.Exit(1)
    console.print(f"  [dim]{verbo}. Vale a partir da próxima sessão do Claude Code.[/]\n")


@app.command("off")
def off(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Tira o RAGX do Claude Code, em todos os projetos: só o Claude, sem o RAGX."""
    from ragx.clients import unregister_all

    _report(unregister_all(dry_run=dry_run, only=[_CLIENT]), "RAGX desligado", as_json)


@app.command("on")
def on(
    command: Annotated[
        str, typer.Option("--command", help="Executável do RAGX gravado na configuração.")
    ] = "ragx",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Põe o RAGX de volta no Claude Code, em todos os projetos."""
    from ragx.clients import register_all

    _report(register_all(command=command, dry_run=dry_run, only=[_CLIENT]), "RAGX ligado", as_json)


@app.command("status")
def status(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Diz se o Claude Code está com o RAGX ligado agora."""
    from ragx.clients import is_registered

    client = _client()
    enabled = is_registered(client)
    if as_json:
        console.print_json(
            json.dumps({"enabled": enabled, "config": str(client.config)}, ensure_ascii=False)
        )
        return
    marca = "[green]ligado[/]" if enabled else "[yellow]desligado[/]"
    console.print(f"\n  RAGX no Claude Code: {marca}  [dim]{escape(str(client.config))}[/]\n")

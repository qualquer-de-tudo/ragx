"""`ragx claude on|off|status|hint` — liga e desliga o RAGX no Claude Code, para todos os projetos.

"Claude Code" aqui é cada perfil dele na máquina: o padrão (`~/.claude.json`)
e os separados por `CLAUDE_CONFIG_DIR` (ex.: `~/.claude-empresa`). Ligar em um
só deixava a outra conta sem o RAGX, sem aviso.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
app = typer.Typer(no_args_is_help=True)


def _perfis():
    from ragx.clients import CLIENTS
    from ragx.clients.registry import CLAUDE_CODE

    return [c for c in CLIENTS() if c.id.split(":", 1)[0] == CLAUDE_CODE and c.installed]


def _estado() -> list[dict[str, object]]:
    from ragx.clients import is_registered
    from ragx.clients.claude_hint import has_hint

    return [
        {
            "id": c.id,
            "label": c.label,
            "config": str(c.config),
            "enabled": is_registered(c),
            "hint": has_hint(c),
        }
        for c in _perfis()
    ]


def _report(results, verbo: str, as_json: bool) -> None:
    ok = all(r.ok for r in results)
    if as_json:
        perfis = _estado()
        payload: dict[str, object] = {
            # O painel mostra UM interruptor: ligado só se todos os perfis estão.
            "enabled": bool(perfis) and all(p["enabled"] for p in perfis),
            "changed": any(r.outcome.value in ("created", "updated", "removed") for r in results),
            "detail": "; ".join(f"{r.client.label}: {r.detail}" for r in results),
            "profiles": perfis,
        }
        if not ok:
            payload["error"] = "; ".join(r.detail for r in results if not r.ok)
        console.print_json(json.dumps(payload, ensure_ascii=False))
        raise typer.Exit(0 if ok else 1)
    console.print()
    for r in results:
        console.print(f"  [cyan]{escape(r.client.label)}[/] {escape(r.detail)}")
        if r.backup:
            console.print(f"      [dim]backup: {r.backup.name}[/]")
    if not ok:
        raise typer.Exit(1)
    console.print(f"  [dim]{verbo}. Vale a partir da próxima sessão do Claude Code.[/]\n")


@app.command("off")
def off(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Tira o RAGX do Claude Code, em todos os projetos e perfis: só o Claude, sem o RAGX."""
    from ragx.clients import unregister
    from ragx.clients.claude_hint import remove_hint

    results = []
    for c in _perfis():
        results.append(unregister(c, dry_run=dry_run))
        results.append(remove_hint(c, dry_run=dry_run))
    _report(results, "RAGX desligado", as_json)


@app.command("on")
def on(
    command: Annotated[
        str, typer.Option("--command", help="Executável do RAGX gravado na configuração.")
    ] = "ragx",
    hint: Annotated[
        bool,
        typer.Option(
            "--hint/--no-hint",
            help="Instala o hook que, no início da sessão, avisa o agente que o projeto tem RAGX.",
        ),
    ] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Põe o RAGX de volta no Claude Code, em todos os projetos e perfis."""
    from ragx.clients import register
    from ragx.clients.claude_hint import install_hint

    results = []
    for c in _perfis():
        r = register(c, command=command, dry_run=dry_run)
        results.append(r)
        if hint and r.ok:
            results.append(install_hint(c, command=command, dry_run=dry_run))
    _report(results, "RAGX ligado", as_json)


@app.command("status")
def status(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Diz, por perfil do Claude Code, se o RAGX está ligado agora."""
    from ragx.clients import CLIENTS
    from ragx.clients.registry import CLAUDE_CODE

    perfis = _estado()
    padrao = next(c for c in CLIENTS() if c.id == CLAUDE_CODE)
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "enabled": bool(perfis) and all(p["enabled"] for p in perfis),
                    "config": str(padrao.config),
                    "profiles": perfis,
                },
                ensure_ascii=False,
            )
        )
        return
    console.print()
    if not perfis:
        console.print("  [yellow]Claude Code não encontrado nesta máquina.[/]\n")
        return
    for p in perfis:
        marca = "[green]ligado[/]" if p["enabled"] else "[yellow]desligado[/]"
        dica = "" if not p["enabled"] else ("  dica: sim" if p["hint"] else "  [yellow]dica: não[/]")
        console.print(
            f"  {escape(str(p['label']))}: {marca}{dica}  [dim]{escape(str(p['config']))}[/]"
        )
    console.print()


@app.command("hint")
def hint() -> None:
    """Texto que o hook de início de sessão entrega ao agente. Vazio fora de projeto RAGX.

    Nunca falha: um erro aqui atrasaria ou sujaria o início de TODA sessão do
    Claude Code, em qualquer pasta.
    """
    import sys

    try:
        from ragx.clients.claude_hint import hint_text

        texto = hint_text()
    except Exception:
        return
    if texto:
        # Direto no stdout, sem Rich: o texto vai para o contexto do agente, e
        # quebra de linha ou markup do terminal viraria ruído lá. Bytes UTF-8:
        # no Windows, stdout em pipe sai em cp1252 e os acentos chegariam ao
        # agente como lixo.
        dados = (texto + "\n").encode("utf-8")
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            sys.stdout.flush()
            buffer.write(dados)
            buffer.flush()
        else:
            sys.stdout.write(texto + "\n")

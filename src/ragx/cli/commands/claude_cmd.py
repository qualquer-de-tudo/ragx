"""`ragx claude on|off|status|hint|profiles` — liga e desliga o RAGX no Claude Code, para todos os projetos.

"Claude Code" aqui é cada perfil dele na máquina: o padrão (`~/.claude.json`),
os separados por `CLAUDE_CONFIG_DIR` (ex.: `~/.claude-empresa`) e as pastas
adicionadas à mão (`ragx claude profiles add`). Ligar em um só deixava a outra
conta sem o RAGX, sem aviso; `--profile` age num perfil só.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
app = typer.Typer(no_args_is_help=True)
profiles_app = typer.Typer(no_args_is_help=True, help="Perfis do Claude Code: listar, adicionar e tirar pastas.")
app.add_typer(profiles_app, name="profiles")

ProfileOpt = Annotated[
    str | None,
    typer.Option("--profile", help="Só neste perfil: o id (claude-code:empresa) ou o nome (empresa, padrão)."),
]


def _perfis(profile: str | None = None):
    from ragx.clients import CLIENTS
    from ragx.clients.registry import CLAUDE_CODE

    perfis = [c for c in CLIENTS() if c.id.split(":", 1)[0] == CLAUDE_CODE and c.installed]
    if profile is None:
        return perfis
    alvo = profile.strip().lower()
    achados = [c for c in perfis if alvo in (c.id.lower(), _nome(c).lower())]
    if not achados:
        nomes = ", ".join(_nome(c) for c in perfis) or "nenhum"
        console.print(f"[red]perfil {escape(profile)!r} não encontrado[/] [dim](perfis: {escape(nomes)})[/]")
        raise typer.Exit(2)
    return achados


def _nome(c) -> str:
    return c.id.split(":", 1)[1] if ":" in c.id else "padrão"


def _estado() -> list[dict[str, object]]:
    from ragx.clients import is_registered
    from ragx.clients.claude_hint import has_hint, has_touch_hook

    return [
        {
            "id": c.id,
            "name": _nome(c),
            "label": c.label,
            "config": str(c.config),
            # A pasta do perfil: `~/.claude` no padrão, a do CLAUDE_CONFIG_DIR nos outros.
            "dir": str(c.config.parent / ".claude") if ":" not in c.id else str(c.config.parent),
            "enabled": is_registered(c),
            "hint": has_hint(c),
            "touch": has_touch_hook(c),
            "added": c.added,
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
    profile: ProfileOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Tira o RAGX do Claude Code, em todos os projetos e perfis (ou só em `--profile`)."""
    from ragx.clients import unregister
    from ragx.clients.claude_hint import remove_hint, remove_touch_hook

    results = []
    for c in _perfis(profile):
        results.append(unregister(c, dry_run=dry_run))
        results.append(remove_hint(c, dry_run=dry_run))
        results.append(remove_touch_hook(c, dry_run=dry_run))
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
    touch: Annotated[
        bool,
        typer.Option(
            "--touch/--no-touch",
            help="Instala o hook que avisa o RAGX de cada arquivo que o agente edita (reindexa só ele).",
        ),
    ] = True,
    profile: ProfileOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Põe o RAGX no Claude Code, em todos os projetos e perfis (ou só em `--profile`)."""
    from ragx.clients import register
    from ragx.clients.claude_hint import install_hint, install_touch_hook, remove_touch_hook

    results = []
    for c in _perfis(profile):
        r = register(c, command=command, dry_run=dry_run)
        results.append(r)
        if hint and r.ok:
            results.append(install_hint(c, command=command, dry_run=dry_run))
        if r.ok:
            results.append(
                install_touch_hook(c, command=command, dry_run=dry_run)
                if touch else remove_touch_hook(c, dry_run=dry_run)
            )
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

    Entrega UMA vez por sessão (o stdin traz `session_id` e `source`) e nunca falha: um erro aqui
    atrasaria ou sujaria o início de TODA sessão do Claude Code, em qualquer pasta. A lógica vive em
    `ragx.hooklight`, a mesma que `ragx.entry` roda sem importar a CLI.
    """
    from ragx.hooklight import run_hint

    run_hint()


# ── perfis adicionados à mão ────────────────────────────────────────────
def _resposta(ok: bool, mudou: bool, detalhe: str, as_json: bool) -> None:
    if as_json:
        payload: dict[str, object] = {"ok": ok, "changed": mudou, "detail": detalhe, "profiles": _estado()}
        if not ok:
            payload["error"] = detalhe
        console.print_json(json.dumps(payload, ensure_ascii=False))
    else:
        cor = "green" if ok else "red"
        console.print(f"\n  [{cor}]{escape(detalhe)}[/]\n")
    if not ok:
        raise typer.Exit(1)


@profiles_app.command("list")
def profiles_list(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Os perfis do Claude Code que o RAGX enxerga, detectados e adicionados."""
    if as_json:
        console.print_json(json.dumps(_estado(), ensure_ascii=False))
        return
    console.print()
    for p in _estado():
        origem = "adicionado" if p["added"] else "detectado"
        marca = "[green]ligado[/]" if p["enabled"] else "[yellow]desligado[/]"
        console.print(f"  {escape(str(p['name']))}: {marca}  [dim]{origem} · {escape(str(p['dir']))}[/]")
    console.print()


@profiles_app.command("add")
def profiles_add(
    pasta: Annotated[str, typer.Argument(help="A pasta do perfil (o CLAUDE_CONFIG_DIR daquela conta).")],
    ligar: Annotated[bool, typer.Option("--on/--no-on", help="Já liga o RAGX nele.")] = False,
    command: Annotated[str, typer.Option("--command", help="Executável do RAGX gravado ao ligar.")] = "ragx",
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Adiciona uma pasta de perfil do Claude Code que a descoberta não acha sozinha."""
    from pathlib import Path

    from ragx.clients import register
    from ragx.clients.claude_hint import install_hint
    from ragx.clients.registry import add_claude_profile

    try:
        mudou, detalhe = add_claude_profile(Path(pasta))
    except ValueError as exc:
        _resposta(False, False, str(exc), as_json)
        return
    if ligar:
        alvo = next(c for c in _perfis() if c.config.parent.resolve() == Path(pasta).expanduser().resolve())
        r = register(alvo, command=command)
        if r.ok:
            install_hint(alvo, command=command)
        detalhe += f"; {r.detail}"
    _resposta(True, mudou, detalhe, as_json)


@profiles_app.command("remove")
def profiles_remove(
    pasta: Annotated[str, typer.Argument(help="A pasta adicionada antes.")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Tira uma pasta da lista. Não mexe na configuração dela: para tirar o RAGX de lá, `off --profile` antes."""
    from pathlib import Path

    from ragx.clients.registry import remove_claude_profile

    mudou, detalhe = remove_claude_profile(Path(pasta))
    _resposta(True, mudou, detalhe, as_json)

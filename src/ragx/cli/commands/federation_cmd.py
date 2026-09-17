"""`ragx federation`, `ragx project`, `ragx hub`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()

federation_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
hub_app = typer.Typer(no_args_is_help=True)


# ── federation ──────────────────────────────────────────────────────────
@federation_app.command("build")
def build(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Gera knowledge/federation/ — a superfície pública deste projeto."""
    from ragx.federation import slice as fed_slice

    cfg = load_config()
    r = fed_slice.build(cfg)
    if as_json:
        console.print_json(json.dumps({
            "path": r.path, "provides": r.provides, "consumes": r.consumes,
            "contracts": r.contracts, "bytes": r.bytes_written,
            "redacted": r.redacted, "private": r.skipped_private,
            "warnings": r.warnings,
        }, ensure_ascii=False))
        return
    if r.skipped_private:
        console.print(
            "\n[yellow]Projeto marcado como `private`[/] — nenhuma fatia gerada.\n"
        )
        return
    console.print(f"\n[bold green]Fatia de federação[/] — {r.path}\n")
    console.print(f"  provides   {r.provides:>5}")
    console.print(f"  consumes   {r.consumes:>5}")
    console.print(f"  contracts  {r.contracts:>5}")
    console.print(f"\n  {r.bytes_written / 1024:.1f} KB")
    if r.redacted:
        console.print(f"  [yellow]{r.redacted} item(ns) descartados pelo re-scan[/]")
    for w in r.warnings:
        console.print(f"  [yellow]! {w}[/]")
    console.print()


@federation_app.command("show")
def show(
    direction: Annotated[str | None, typer.Option("--direction")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mostra a superfície pública deste projeto."""
    from ragx.federation import slice as fed_slice

    cfg = load_config()
    folder = cfg.root / "knowledge" / fed_slice.FOLDER
    if not folder.is_dir():
        console.print("\n[yellow]sem fatia.[/] Rode: [bold]ragx federation build[/]\n")
        raise typer.Exit(1)
    data = fed_slice.load(folder)
    if as_json:
        console.print_json(json.dumps(data, ensure_ascii=False))
        return
    svc = data.get("service", {})
    console.print(f"\n[bold]{svc.get('name')}[/]  [dim]{svc.get('project_id')}[/]\n")
    for d in ("provides", "consumes"):
        if direction and d != direction:
            continue
        console.print(f"[bold cyan]{d}[/]")
        for kind, entries in (data.get(d) or {}).items():
            for e in entries or []:
                conf = "" if e.get("confidence", 1) >= 1 else f"  [dim]{e['confidence']}[/]"
                console.print(f"  [yellow]{kind:<8}[/] {e['normalized']:<40} [dim]{e['source']}[/]{conf}")
        console.print()


@federation_app.command("export")
def export_slice(target: Annotated[Path, typer.Argument()]) -> None:
    """Exporta a fatia como arquivo único (.fed.json), para quem não clona o repo."""
    from ragx.federation import slice as fed_slice

    cfg = load_config()
    n = fed_slice.export_file(cfg, target)
    console.print(f"\n[green]✓[/] {target}  [dim]{n / 1024:.1f} KB[/]\n")


# ── project ─────────────────────────────────────────────────────────────
@project_app.command("register")
def register(
    path: Annotated[Path | None, typer.Argument()] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    from_federation: Annotated[Path | None, typer.Option("--from-federation")] = None,
    visibility: Annotated[str | None, typer.Option("--visibility")] = None,
) -> None:
    """Registra um projeto no hub (clonado ou só pela fatia)."""
    from ragx.federation import hub as hub_mod

    cfg = load_config()
    ref = hub_mod.register(cfg, path, name, from_federation, visibility)
    estado = "clonado" if ref.cloned else "só-federação"
    console.print(f"\n[green]✓[/] {ref.name}  [dim]{ref.id} · {estado}[/]\n")


@project_app.command("list")
def list_(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Projetos registrados."""
    from ragx.federation import hub as hub_mod

    rows = hub_mod.list_projects(load_config())
    if as_json:
        console.print_json(json.dumps(rows, ensure_ascii=False, default=str))
        return
    if not rows:
        console.print("\n[dim]nenhum projeto registrado[/]\n")
        return
    console.print()
    for r in rows:
        estado = "clonado" if r["cloned"] else "federação"
        cor = {"ok": "green", "degraded": "yellow", "missing": "red", "stale": "yellow"}
        console.print(
            f"  [{cor.get(r['status'], 'white')}]{r['status']:<9}[/] "
            f"{r['name']:<24} [cyan]{estado:<10}[/] [dim]{r['path'] or '—'}[/]"
        )
    console.print(f"\n  {len(rows)} projeto(s)\n")


@project_app.command("unregister")
def unregister(name: Annotated[str, typer.Argument()]) -> None:
    """Remove um projeto do hub."""
    from ragx.federation import hub as hub_mod

    if hub_mod.unregister(load_config(), name):
        console.print(f"\n[green]✓[/] {name} removido\n")
    else:
        console.print(f"\n[yellow]{name} não estava registrado[/]\n")
        raise typer.Exit(1)


# ── hub ─────────────────────────────────────────────────────────────────
@hub_app.command("sync")
def hub_sync(
    project: Annotated[str | None, typer.Option("--project")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Atualiza o hub a partir dos projetos registrados."""
    from ragx.federation import hub as hub_mod

    cfg = load_config()
    r = hub_mod.sync(cfg, project)
    if as_json:
        console.print_json(json.dumps({
            "synced": r.synced, "skipped": r.skipped, "items": r.items,
            "redacted": r.redacted, "warnings": r.warnings,
        }, ensure_ascii=False))
        return
    console.print(f"\n[bold]Hub sync[/] — {hub_mod.hub_dir(cfg)}\n")
    for name in r.synced:
        console.print(f"  [green]✓[/] {name}")
    for name, why in r.skipped.items():
        console.print(f"  [dim]· {name}: {why}[/]")
    console.print(f"\n  {r.items} item(ns) de federação")
    if r.redacted:
        console.print(f"  [yellow]{r.redacted} descartado(s) pelo re-scan na entrada[/]")
    for w in r.warnings:
        console.print(f"  [yellow]! {w}[/]")
    console.print()


@hub_app.command("status")
def hub_status(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Estado do hub e de cada projeto."""
    from ragx.federation import hub as hub_mod

    st = hub_mod.status(load_config())
    if as_json:
        console.print_json(json.dumps(st, ensure_ascii=False, default=str))
        return
    if not st["projects"]:
        console.print("\n[dim]hub vazio — `ragx project register <caminho>`[/]\n")
        raise typer.Exit(1)
    console.print("\n[bold]Hub[/]\n")
    for p in st["projects"]:
        cor = {"ok": "green", "degraded": "yellow", "missing": "red", "stale": "yellow"}
        console.print(
            f"  [{cor.get(p['status'], 'white')}]{p['status']:<9}[/] {p['name']:<24} "
            f"[dim]{p['last_sync'] or 'nunca sincronizado'}[/]"
        )
    console.print(
        f"\n  {st['items']} itens · {st['links']} vínculos · "
        f"{st['unresolved']} não resolvido(s)\n"
    )


@hub_app.command("link")
def hub_link(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Resolve consumes ⟷ provides entre os projetos."""
    from ragx.federation import linker

    cfg = load_config()
    r = linker.link(cfg)
    if as_json:
        console.print_json(json.dumps({
            "links": [lk.__dict__ for lk in r.links],
            "unresolved": r.unresolved, "divergences": r.divergences,
            "suggestions": r.suggestions,
        }, ensure_ascii=False))
        return
    console.print()
    if r.links:
        console.print(f"  [bold green]Vínculos resolvidos ({len(r.links)})[/]")
        for lk in r.links:
            console.print(
                f"    {lk.src_project:<20} [yellow]--{lk.relation}-->[/] "
                f"{lk.dst_project:<20} {lk.normalized:<28} {lk.confidence:.2f}"
            )
        console.print()
    if r.unresolved:
        console.print(f"  [bold yellow]Consumos sem provedor conhecido ({len(r.unresolved)})[/]")
        for u in r.unresolved:
            console.print(f"    {u['from']} → {u['target']}")
            console.print("      [dim]nenhum projeto registrado provê isto — "
                          "registre o repositório, ou é integração de terceiro[/]")
        console.print()
    if r.divergences:
        console.print(f"  [bold red]Divergências ({len(r.divergences)})[/]")
        for d in r.divergences:
            console.print(f"    {d['from']} consome  {d['consumed']}")
            console.print(f"    {d['to']} provê     {d['provided']}")
            console.print(f"      [dim]{d['issue']} — possível bug de integração[/]")
        console.print()
    if not (r.links or r.unresolved or r.divergences):
        console.print("  [dim]nada a resolver — rode `ragx hub sync` antes[/]\n")


@hub_app.command("dictionary")
def hub_dictionary(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Dicionário de workspace: quem fala com quem."""
    from ragx.federation import linker

    data = linker.workspace_dictionary(load_config())
    if as_json:
        console.print_json(json.dumps(data, ensure_ascii=False))
        return
    console.print("\n[bold]Workspace[/]\n")
    for p in data["projects"]:
        marca = "" if p["cloned"] else "  [dim](só federação)[/]"
        console.print(f"  {p['name']}{marca}")
    if data["integrations"]:
        console.print("\n[bold cyan]Integrações[/]")
        for i in data["integrations"]:
            console.print(f"  {i['from']} → {i['to']}  [dim]{i['via']}  {i['confidence']}[/]")
    if data["unresolved_consumes"]:
        console.print("\n[bold yellow]Sem provedor[/]")
        for u in data["unresolved_consumes"]:
            console.print(f"  {u['from']} → {u['target']}")
    if data["divergences"]:
        console.print("\n[bold red]Divergências[/]")
        for d in data["divergences"]:
            console.print(f"  {d['from']} → {d['target']}  [dim]{d['detail']}[/]")
    console.print()


@hub_app.command("reset")
def hub_reset(
    yes: Annotated[bool, typer.Option("--yes", help="Não perguntar.")] = False,
) -> None:
    """Apaga o hub. Reconstruível com `ragx hub sync`."""
    from ragx.federation import hub as hub_mod

    cfg = load_config()
    if not yes:
        alvo = hub_mod.hub_dir(cfg)
        if not typer.confirm(f"Apagar {alvo}?"):
            raise typer.Exit(1)
    hub_mod.reset(cfg)
    console.print("\n[green]✓[/] hub apagado\n")


def contract(
    name: Annotated[str, typer.Argument(help="Ex.: 'POST /api/payments'")],
    kind: Annotated[str, typer.Option("--kind")] = "http",
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Contrato de um endpoint ou evento, e o projeto que o provê."""
    from ragx.federation import linker

    cfg = load_config()
    found = linker.find_contract(cfg, kind, name)
    if found is None:
        raise UsageError(f"contrato não encontrado: {kind} {name!r}")
    if as_json:
        console.print_json(json.dumps(found, ensure_ascii=False, default=str))
        return
    console.print(f"\n[bold]{found['normalized']}[/]  [cyan]({found['kind']})[/]")
    console.print(f"  provido por  [green]{found['project']}[/]")
    console.print(f"  handler      {found['handler'] or '—'}")
    console.print(f"  fonte        [dim]{found['source_ref']}[/]")
    if found["contract_body"]:
        console.print(f"\n{found['contract_body'][:2000]}")
    console.print()

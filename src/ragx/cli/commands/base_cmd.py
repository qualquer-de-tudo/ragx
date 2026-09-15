"""`ragx base` — conhecimento base compartilhado entre projetos.

Regras de arquitetura, guardrails e padrões não pertencem a um repositório:
valem para todos. Ficam uma vez por máquina em `~/.ragx/base/` e entram no
índice de cada projeto sob `@base/<fonte>/`.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ragx.base import source as base_source
from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()
app = typer.Typer(help="Conhecimento base compartilhado entre projetos.", no_args_is_help=True)


@app.command("add")
def add_cmd(
    origin: Annotated[str, typer.Argument(help="URL do Git ou caminho local.")],
    name: Annotated[str | None, typer.Option("--name", help="Nome curto da fonte.")] = None,
    ref: Annotated[str | None, typer.Option("--ref", help="Branch ou tag.")] = None,
    index: Annotated[bool, typer.Option("--index/--no-index", help="Indexar em seguida.")] = True,
    declare: Annotated[
        bool,
        typer.Option(
            "--declare/--no-declare",
            help="Declarar a fonte no ragx.toml deste projeto.",
        ),
    ] = True,
) -> None:
    """Registra uma fonte de conhecimento base nesta máquina.

    Instalar não basta para indexar: o projeto precisa DECLARAR a fonte em
    `ragx.toml` — é o que impede que um `base add` mude em silêncio o índice de
    todos os outros projetos da máquina, e é o que viaja no Git.
    """
    cfg = load_config()
    r = base_source.add(cfg, origin, name=name, ref=ref)
    console.print(
        f"\n[green]✓[/] [bold]{r.name}[/] — {r.files} arquivos"
        + (f"  [dim]{r.commit[:8]}[/]" if r.commit else "")
        + f"\n  [dim]{r.path}[/]"
    )

    if declare and _declare(cfg, origin):
        console.print(f"  [green]✓[/] declarada em [dim]{cfg.root / 'ragx.toml'}[/]")
        cfg = load_config()  # recarrega para que a indexação já enxergue
    elif not declare:
        console.print(
            "\n  [yellow]não declarada[/] — esta fonte NÃO será indexada até que"
            f"\n  [bold]\\[base] sources[/] em ragx.toml contenha [bold]{origin}[/]"
        )
        index = False

    if index:
        console.print("\n  [dim]indexando…[/]")
        _reindex(cfg)
    console.print()


def _declare(cfg: object, origin: str) -> bool:
    """Insere a origem em `[base] sources` preservando comentários do arquivo.

    Reescrever o TOML a partir do parser apagaria todo comentário — e este
    arquivo é onde as decisões do projeto ficam explicadas. Então a edição é
    textual e cirúrgica.
    """
    import tomllib

    path = cfg.root / "ragx.toml"  # type: ignore[attr-defined]
    texto = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        atual = tomllib.loads(texto).get("base", {}).get("sources", [])
    except tomllib.TOMLDecodeError:
        return False
    if origin in atual:
        return False

    novas = json.dumps([*atual, origin], ensure_ascii=False)
    linha = f"sources = {novas}"
    linhas = texto.splitlines()

    alvo = next((i for i, ln in enumerate(linhas) if ln.strip() == "[base]"), None)
    if alvo is None:
        texto = texto.rstrip("\n") + f"\n\n[base]\n{linha}\n"
    else:
        fim = next(
            (i for i in range(alvo + 1, len(linhas)) if linhas[i].lstrip().startswith("[")),
            len(linhas),
        )
        existente = next(
            (i for i in range(alvo + 1, fim) if linhas[i].lstrip().startswith("sources")),
            None,
        )
        if existente is None:
            linhas.insert(alvo + 1, linha)
        else:
            linhas[existente] = linha
        texto = "\n".join(linhas) + "\n"

    path.write_text(texto, encoding="utf-8", newline="\n")
    return True


@app.command("list")
def list_cmd(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Fontes registradas nesta máquina."""
    cfg = load_config()
    sources = base_source.load_registry(cfg)
    if as_json:
        console.print_json(json.dumps(
            {"sources": [s.to_dict() for s in sources]}, ensure_ascii=False
        ))
        return
    if not sources:
        console.print(
            "\n[dim]nenhuma fonte base.[/]"
            "\n  [bold]ragx base add <url-do-git>[/]\n"
        )
        return
    table = Table(box=None, pad_edge=False)
    table.add_column("fonte", style="bold")
    table.add_column("arquivos", justify="right")
    table.add_column("commit", style="dim")
    table.add_column("origem", style="dim", overflow="fold")
    for s in sources:
        marca = "" if s.enabled else " [yellow](off)[/]"
        table.add_row(
            s.name + marca, str(s.files), (s.commit or "—")[:8], s.origin
        )
    # Uma string só: `console.print(a, b, c)` separa os argumentos e o `[/]`
    # final ficaria sem par, estourando o parser de markup do Rich.
    console.print(f"\n[bold]Conhecimento base[/]  [dim]{base_source.base_dir(cfg)}[/]\n")
    console.print(table)
    console.print()


@app.command("update")
def update_cmd(
    name: Annotated[str | None, typer.Argument(help="Fonte. Vazio = todas.")] = None,
    index: Annotated[bool, typer.Option("--index/--no-index")] = True,
) -> None:
    """Rebaixa as fontes e reindexa o que mudou."""
    cfg = load_config()
    reports = base_source.update(cfg, name)
    console.print()
    mudou = False
    for r in reports:
        if r.warnings:
            for w in r.warnings:
                console.print(f"  [yellow]![/] {r.name}: {w}")
            continue
        estado = "[green]atualizada[/]" if r.updated else "[dim]sem mudança[/]"
        mudou = mudou or r.updated
        console.print(f"  [bold]{r.name}[/] {estado}  [dim]{r.files} arquivos[/]")
    if index and mudou:
        console.print("\n  [dim]reindexando…[/]")
        _reindex(cfg)
    console.print()


@app.command("sync")
def sync_cmd(
    index: Annotated[bool, typer.Option("--index/--no-index")] = True,
) -> None:
    """Instala as fontes que ESTE projeto exige e faltam nesta máquina.

    Lê `ragx.toml` e `knowledge/base.json`. É o comando que quem clona o
    repositório roda uma vez.
    """
    cfg = load_config()
    declaradas = base_source.declared_for(cfg)
    if not declaradas:
        console.print(
            "\n[dim]este projeto não declara conhecimento base.[/]"
            "\n  [dim]Adicione em ragx.toml:[/] [bold]\\[base] sources = [...][/]\n"
        )
        return

    reports = base_source.sync_declared(cfg, declaradas)
    console.print()
    if not reports:
        console.print("  [dim]tudo já instalado.[/]\n")
        return
    for r in reports:
        if r.warnings:
            for w in r.warnings:
                console.print(f"  [yellow]![/] {r.name}: {w}")
        else:
            console.print(f"  [green]+[/] [bold]{r.name}[/]  [dim]{r.files} arquivos[/]")
    if index:
        console.print("\n  [dim]indexando…[/]")
        _reindex(cfg)
    console.print()


@app.command("remove")
def remove_cmd(
    name: Annotated[str, typer.Argument(help="Fonte a remover.")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Remove uma fonte desta máquina. Os documentos saem no próximo index."""
    cfg = load_config()
    if not yes and not typer.confirm(f"Remover a fonte base '{name}'?"):
        raise typer.Exit(1)
    if not base_source.remove(cfg, name):
        raise UsageError(f"fonte não encontrada: {name}")
    console.print(
        f"\n[green]✓[/] {name} removida."
        "\n  [dim]Rode `ragx index .` para tirar os documentos do índice.[/]\n"
    )


@app.command("enable")
def enable_cmd(name: Annotated[str, typer.Argument()]) -> None:
    """Volta a indexar uma fonte desligada."""
    _toggle(name, True)


@app.command("disable")
def disable_cmd(name: Annotated[str, typer.Argument()]) -> None:
    """Para de indexar a fonte sem apagá-la do disco."""
    _toggle(name, False)


def _toggle(name: str, enabled: bool) -> None:
    cfg = load_config()
    if not base_source.set_enabled(cfg, name, enabled):
        raise UsageError(f"fonte não encontrada: {name}")
    estado = "habilitada" if enabled else "desabilitada"
    console.print(f"\n[green]✓[/] {name} {estado}. [dim]Rode `ragx index .`.[/]\n")


def _reindex(cfg: object) -> None:
    from ragx.indexing.pipeline import index_project

    r = index_project(cfg)  # type: ignore[arg-type]
    console.print(
        f"  [green]✓[/] {r.stats.indexed} indexados, {r.stats.chunks} chunks"
        + (f", [yellow]{r.stats.blocked} bloqueados[/]" if r.stats.blocked else "")
    )

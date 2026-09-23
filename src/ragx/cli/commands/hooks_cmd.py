"""`ragx hooks install|uninstall|status` e o oculto `ragx hook-run`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import find_root

console = Console()
app = typer.Typer(no_args_is_help=True)


def _root(path: Path) -> Path:
    root, _found = find_root(path.resolve())
    return root


@app.command("install")
def install(path: Annotated[Path, typer.Argument()] = Path(".")) -> None:
    """Instala os hooks que reindexam ao trocar de branch, commitar e fazer merge."""
    from ragx import githooks

    root = _root(path)
    written = githooks.install(root)
    console.print(f"\n[green]Hooks instalados[/] para {root}")
    for p in written:
        console.print(f"  [green]+[/] {p}")
    console.print("  [dim]Desative por um comando com RAGX_SKIP_HOOK=1[/]\n")


@app.command("uninstall")
def uninstall(path: Annotated[Path, typer.Argument()] = Path(".")) -> None:
    """Remove só os blocos do RAGX deste projeto; o resto dos hooks fica."""
    from ragx import githooks

    root = _root(path)
    touched = githooks.uninstall(root)
    if not touched:
        console.print("\n[dim]Nenhum hook do RAGX para este projeto.[/]\n")
        return
    console.print(f"\n[green]Hooks removidos[/] de {root}")
    for p in touched:
        console.print(f"  [red]-[/] {p}")
    console.print()


@app.command("status")
def status(
    path: Annotated[Path, typer.Argument()] = Path("."),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mostra se os hooks deste projeto estão instalados."""
    from ragx import githooks

    st = githooks.state(_root(path))
    if as_json:
        console.print_json(json.dumps(st, ensure_ascii=False))
        return
    if st["hooks_dir"] is None:
        console.print("\n[yellow]Fora de um repositório git.[/]\n")
        return
    console.print(f"\n[bold]Hooks[/] em {st['hooks_dir']}\n")
    for event, ok in st["events"].items():
        mark = "[green]instalado[/]" if ok else "[dim]ausente[/]"
        console.print(f"  {event:<14} {mark}")
    console.print()


def hook_run(
    event: Annotated[str, typer.Argument()],
    root: Annotated[Path, typer.Option("--root")],
    args: Annotated[list[str] | None, typer.Argument()] = None,
) -> None:
    """Uso interno dos hooks de git: dispara a indexação destacada e sai."""
    from ragx import githooks

    if event not in githooks.EVENTS:
        raise typer.Exit(0)
    if not githooks.should_run(event, list(args or [])):
        raise typer.Exit(0)
    if not (root / "ragx.toml").exists():
        raise typer.Exit(0)
    githooks.spawn_index(root, event)

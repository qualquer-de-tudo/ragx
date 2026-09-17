"""`ragx context` — contexto pronto para um prompt, dentro de um orçamento."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()
_FORMATS = ("markdown", "json", "xml")


def context(
    query: Annotated[str, typer.Argument(help="Tarefa ou pergunta.")],
    tokens: Annotated[int, typer.Option("--tokens", min=200, max=200_000)] = 0,
    fmt: Annotated[str, typer.Option("--format", help="markdown|json|xml")] = "markdown",
    include_graph: Annotated[bool, typer.Option("--include-graph/--no-graph")] = True,
    depth: Annotated[int | None, typer.Option("--depth", min=1, max=3)] = None,
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    path_glob: Annotated[str | None, typer.Option("--path")] = None,
    explain: Annotated[bool, typer.Option("--explain", help="Por que cada trecho entrou/saiu.")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
    out: Annotated[Path | None, typer.Option("--out", help="Grava em arquivo.")] = None,
) -> None:
    """Monta o contexto de trabalho para uma tarefa."""
    from ragx.context.engine import build_context
    from ragx.context.render import explain as render_explain
    from ragx.context.render import render
    from ragx.search.service import SearchFilters

    if fmt not in _FORMATS:
        raise UsageError(f"formato inválido: {fmt!r} (use {' | '.join(_FORMATS)})")

    cfg = load_config()
    pack = build_context(
        cfg, query,
        budget=tokens or cfg.context.default_tokens,
        include_graph=include_graph,
        depth=depth,
        filters=SearchFilters(lang=lang, path_glob=path_glob),
        use_cache=not no_cache,
    )

    if not pack.fragments:
        console.print(f"\n[dim]nenhum contexto para[/] [bold]{query}[/]\n")
        raise typer.Exit(1)

    body = render(pack, fmt)

    if out is not None:
        # sem códigos ANSI: o arquivo é para ser lido por outra ferramenta
        out.write_text(body, encoding="utf-8")
        console.print(
            f"\n[green]✓[/] {out}  "
            f"[dim]{len(pack.fragments)} fragmentos · ~{pack.estimated_tokens} tokens[/]\n"
        )
    else:
        print(body)

    if explain:
        console.print()
        console.print(render_explain(pack))
        console.print()
    elif out is None and pack.cached:
        console.print("\n[dim](do cache)[/]")

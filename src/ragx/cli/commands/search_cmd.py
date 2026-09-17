"""`ragx search` — o comando que fecha o MVP vertical."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()

_MODES = ("hybrid", "semantic", "keyword")


def search(
    query: Annotated[str, typer.Argument(help="Consulta em linguagem natural ou símbolo.")],
    mode: Annotated[str | None, typer.Option("--mode", help="hybrid|semantic|keyword")] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    kind: Annotated[str | None, typer.Option("--kind")] = None,
    path_glob: Annotated[str | None, typer.Option("--path")] = None,
    min_score: Annotated[float, typer.Option("--min-score")] = 0.0,
    scope: Annotated[str, typer.Option("--scope", help="current|all|project:<nome>")] = "current",
    raw: Annotated[bool, typer.Option("--raw", help="Interpreta sintaxe FTS5 crua.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Busca no conhecimento indexado."""
    from ragx.search.service import SearchFilters
    from ragx.search.service import search as run_search

    if mode and mode not in _MODES:
        raise UsageError(f"modo inválido: {mode!r} (use {' | '.join(_MODES)})")

    cfg = load_config()
    filters = SearchFilters(lang=lang, kind=kind, path_glob=path_glob, min_score=min_score)

    if scope != "current":
        from ragx.federation.search import search_scoped
        from ragx.search.service import SearchOutcome

        scoped = search_scoped(
            cfg, query, scope=scope, mode=mode or cfg.search.default_mode,
            limit=limit or cfg.search.limit, filters=filters,
        )
        outcome = SearchOutcome(
            results=scoped.results, mode=mode or cfg.search.default_mode,
            degraded="; ".join(f"{k}: {v}" for k, v in scoped.degraded.items()) or None,
        )
    else:
        outcome = run_search(cfg, query, mode=mode, limit=limit, raw=raw, filters=filters)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "query": query,
                    "mode": outcome.mode,
                    "degraded": outcome.degraded,
                    "timings_ms": {k: round(v, 2) for k, v in outcome.timings_ms.items()},
                    "results": [
                        {
                            "chunk_id": r.chunk_id,
                            "project": r.project,
                            "document_path": r.document_path,
                            "symbol": r.symbol,
                            "heading_path": r.heading_path,
                            "kind": r.kind.value,
                            "lines": [r.start_line, r.end_line],
                            "score": round(r.score, 6),
                            "matched_by": list(r.matched_by),
                            "content": r.content,
                            "metadata": r.metadata,
                        }
                        for r in outcome.results
                    ],
                },
                ensure_ascii=False,
            )
        )
        raise typer.Exit(0 if outcome.results else 1)

    if outcome.degraded:
        console.print(f"\n[yellow]![/] {outcome.degraded}")

    if not outcome.results:
        console.print(f"\n[dim]nenhum resultado para[/] [bold]{query}[/]\n")
        raise typer.Exit(1)

    console.print()
    for i, r in enumerate(outcome.results, start=1):
        label = r.heading_path or r.symbol or ""
        loc = f"{r.document_path}:{r.start_line}-{r.end_line}"
        srcs = "+".join(r.matched_by) or outcome.mode
        console.print(
            f"  [bold]{i:>2}[/]  [green]{r.score:.3f}[/]  "
            + (f"[magenta]{r.project}[/]:" if scope != "current" else "")
            + f"{loc}"
            + (f" [cyan]› {label}[/]" if label else "")
            + f"  [dim][{srcs}][/]"
        )
        for line in _snippet(r.content):
            console.print(f"         [dim]{line}[/]")
        console.print()

    timings = " · ".join(f"{k} {v:.0f} ms" for k, v in outcome.timings_ms.items())
    total = sum(outcome.timings_ms.values())
    console.print(f"  {len(outcome.results)} resultado(s) em {total:.0f} ms  [dim]({timings})[/]\n")


def _snippet(content: str, max_lines: int = 3, width: int = 88) -> list[str]:
    out: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        out.append(line[:width] + ("…" if len(line) > width else ""))
        if len(out) >= max_lines:
            break
    return out

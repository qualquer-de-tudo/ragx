"""`ragx entities`, `ragx graph`, `ragx graph-search`, `ragx graph rebuild`."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config

console = Console()


class _GraphGroup(typer.core.TyperGroup):
    """`ragx graph rebuild` e `ragx graph AuthService` na MESMA palavra.

    O Click resolveria "AuthService" como subcomando inexistente e abortaria.
    Aqui, o que não for subcomando conhecido cai em `show` — que é a forma mais
    usada e a que a documentação destaca.
    """

    def resolve_command(self, ctx, args):  # type: ignore[no-untyped-def]
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = ["show", *args]
        return super().resolve_command(ctx, args)


app = typer.Typer(cls=_GraphGroup, no_args_is_help=True)

_ARROW = {"out": "→", "in": "←"}


def entities(
    entity_type: Annotated[str | None, typer.Option("--type")] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lista entidades do grafo."""
    from ragx.graph.store import GraphStore, confidence_tier
    from ragx.storage.db import open_db

    cfg = load_config()
    with open_db(cfg.db_path, read_only=True) as conn:
        rows = GraphStore(conn).list_entities(entity_type, name, limit)
        stats = GraphStore(conn).stats()
    if as_json:
        console.print_json(json.dumps(rows, ensure_ascii=False, default=str))
        return
    if not rows:
        console.print("\n[dim]nenhuma entidade — rode: ragx graph rebuild[/]\n")
        raise typer.Exit(1)
    console.print()
    for r in rows:
        conf = (
            ""
            if r["confidence"] >= 1.0
            else f"  [dim]{r['confidence']:.2f} ({confidence_tier(r['confidence'])})[/]"
        )
        console.print(f"  [cyan]{r['type']:<11}[/] {r['name']:<34} [dim]{r['qualified_name']}[/]{conf}")
    console.print(f"\n  {len(rows)} de {stats.entities} entidades\n")


@app.command("show")
def graph(
    entity: Annotated[str, typer.Argument(help="Nome ou id da entidade.")],
    depth: Annotated[int, typer.Option("--depth", min=1, max=3)] = 1,
    relations: Annotated[str | None, typer.Option("--relations", help="tipo,tipo")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Vizinhança de uma entidade."""
    from ragx.graph.store import GraphStore
    from ragx.graph.traversal import neighborhood
    from ragx.storage.db import open_db

    cfg = load_config()
    rel_types = tuple(r.strip() for r in relations.split(",")) if relations else None

    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        found = store.find(entity)
        if not found:
            console.print(f"\n[red]entidade não encontrada:[/] {entity}")
            nearby = store.list_entities(name=entity[:6], limit=5)
            if nearby:
                console.print("[dim]  talvez:[/] " + ", ".join(n["name"] for n in nearby))
            console.print()
            raise typer.Exit(1)
        target = found[0]
        edges = neighborhood(store, target["id"], depth=depth, relation_types=rel_types)

    if as_json:
        # `nodes` sai junto porque uma aresta só aponta para IDs: sem a lista
        # de nós, quem desenha o grafo recebe `src`/`dst` que não resolvem
        # para nome nenhum. Vinha faltando, e a extensão do VS Code filtrava
        # todas as arestas contra um conjunto de nós vazio — grafo em branco.
        nodes = {
            target["id"]: {
                "id": target["id"], "name": target["name"], "type": target["type"],
                "qualified_name": target["qualified_name"],
                "confidence": target["confidence"], "provenance": target["source"],
            }
        }
        for e in edges:
            nodes.setdefault(
                str(e["other_id"]),
                {
                    "id": e["other_id"], "name": e["other_name"], "type": e["other_type"],
                    "qualified_name": e["other_qname"],
                },
            )
        console.print_json(
            json.dumps(
                {"entity": target, "nodes": list(nodes.values()), "edges": edges},
                ensure_ascii=False,
                default=str,
            )
        )
        return

    console.print(
        f"\n[bold]{target['name']}[/]  [cyan]({target['type']})[/]  "
        f"[dim]{target['qualified_name']}[/]\n"
    )
    if not edges:
        console.print("  [dim]sem relações[/]\n")
        return

    grouped: dict[tuple[str, str], list[str]] = {}
    for e in edges:
        grouped.setdefault((str(e["direction"]), str(e["type"])), []).append(
            f"{e['other_name']} [dim]({e['other_type']})[/]"
        )
    for (direction, rtype), targets in sorted(grouped.items()):
        shown = targets[:6]
        extra = f" [dim]+{len(targets) - 6}[/]" if len(targets) > 6 else ""
        console.print(
            f"  {_ARROW[direction]} [yellow]{rtype:<15}[/] " + ", ".join(shown) + extra
        )
    console.print(f"\n  {len(edges)} relações · profundidade {depth}\n")


def graph_search(
    query: Annotated[str, typer.Argument()],
    depth: Annotated[int | None, typer.Option("--depth", min=1, max=3)] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Busca combinando vetor e grafo."""
    from ragx.graph.service import graph_search as run_graph_search
    from ragx.search.service import SearchFilters

    cfg = load_config()
    out = run_graph_search(
        cfg, query, limit=limit, depth=depth, filters=SearchFilters(lang=lang)
    )
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "query": query,
                    "seeds": out.seeds,
                    "expanded": len(out.expansion.scores),
                    "truncated": out.expansion.truncated,
                    "timings_ms": {k: round(v, 2) for k, v in out.timings_ms.items()},
                    "results": [
                        {
                            "chunk_id": r.chunk_id, "document_path": r.document_path,
                            "symbol": r.symbol, "lines": [r.start_line, r.end_line],
                            "score": round(r.score, 6), "via": r.metadata.get("via"),
                        }
                        for r in out.results
                    ],
                },
                ensure_ascii=False,
            )
        )
        return

    if not out.results:
        console.print(f"\n[dim]nenhum resultado para[/] [bold]{query}[/]\n")
        raise typer.Exit(1)

    console.print()
    for i, r in enumerate(out.results, start=1):
        label = r.heading_path or r.symbol or ""
        via = r.metadata.get("via", "hybrid")
        console.print(
            f"  [bold]{i:>2}[/]  [green]{r.score:.3f}[/]  "
            f"{r.document_path}:{r.start_line}-{r.end_line}"
            + (f" [cyan]› {label}[/]" if label else "")
            + f"  [dim][{via}][/]"
        )
    trunc = " [yellow](truncado)[/]" if out.expansion.truncated else ""
    total = sum(out.timings_ms.values())
    console.print(
        f"\n  {len(out.results)} resultado(s) · {out.seeds} âncoras · "
        f"{len(out.expansion.scores)} nós visitados{trunc} · {total:.0f} ms\n"
    )


@app.command("rebuild")
def rebuild(
    layers: Annotated[str, typer.Option("--layers", help="1,2")] = "1,2",
    semantic: Annotated[bool, typer.Option("--semantic")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Reconstrói o grafo a partir dos chunks já indexados."""
    from ragx.graph.service import rebuild as run_rebuild

    cfg = load_config()
    if semantic:
        console.print(
            "[yellow]![/] camada semântica ainda não implementada (RAGX-0037); "
            "reconstruindo camadas 1-2."
        )
    chosen = tuple(int(x) for x in layers.split(",") if x.strip().isdigit())
    report = run_rebuild(cfg, layers=chosen)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "entities": report.stats.entities,
                    "relations": report.stats.relations,
                    "by_type": report.stats.by_type,
                    "by_relation": report.stats.by_relation,
                    "unresolved": report.unresolved,
                    "pruned": report.pruned,
                    "duration_ms": report.duration_ms,
                },
                ensure_ascii=False,
            )
        )
        return

    console.print(f"\n[bold]Grafo reconstruído[/] — camadas {chosen}\n")
    console.print(f"  Entidades  {report.stats.entities:>8,}")
    for t, n in list(report.stats.by_type.items())[:8]:
        console.print(f"    [cyan]{t:<13}[/] {n:>6,}")
    console.print(f"\n  Relações   {report.stats.relations:>8,}")
    for t, n in list(report.stats.by_relation.items())[:8]:
        console.print(f"    [yellow]{t:<13}[/] {n:>6,}")
    if report.pruned:
        console.print(f"\n  [dim]{report.pruned} relação(ões) órfã(s) removida(s)[/]")
    if report.unresolved:
        console.print(f"  [dim]{report.unresolved} import(s) não resolvido(s) (externos)[/]")
    console.print(f"\n  Tempo {report.duration_ms / 1000:.1f} s\n")

"""GraphService — reconstrução e graph-search (vetor + grafo).

É aqui que o grafo paga o próprio custo: encontrar conhecimento relacionado que
a busca híbrida pura não encontra.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ragx.config import Config
from ragx.core.models import SearchResult
from ragx.graph.extractors import reference, structural
from ragx.graph.store import GraphStats, GraphStore
from ragx.graph.traversal import Expansion, TraversalLimits, expand
from ragx.search.hybrid import rrf
from ragx.search.ranking import diversify, rerank
from ragx.search.service import SearchFilters, search
from ragx.storage.db import open_db


@dataclass
class RebuildReport:
    entities: int = 0
    relations: int = 0
    unresolved: int = 0
    pruned: int = 0
    duration_ms: int = 0
    stats: GraphStats = field(default_factory=GraphStats)


def rebuild(cfg: Config, layers: tuple[int, ...] = (1, 2)) -> RebuildReport:
    """Reconstrói as camadas determinísticas do zero. A camada semântica
    (source='semantic') é preservada — ela custa dinheiro."""
    report = RebuildReport()
    t0 = time.perf_counter()

    with open_db(cfg.db_path) as conn:
        store = GraphStore(conn)
        store.clear(("structural", "reference"))

        by_chunk: dict[str, str] = {}
        if 1 in layers:
            ents, rels, by_chunk = structural.extract(conn)
            report.entities += store.upsert_entities(ents)
            report.relations += store.upsert_relations(rels)

        if 2 in layers:
            res = reference.extract(conn, by_chunk, cfg.root)
            report.entities += store.upsert_entities(res.entities)
            # relações só podem ser gravadas depois das entidades existirem
            known_ids = {
                r["id"] for r in conn.execute("SELECT id FROM entities")
            }
            valid = [
                rel for rel in res.relations
                if rel.src_id in known_ids and rel.dst_id in known_ids
            ]
            report.relations += store.upsert_relations(valid)
            report.unresolved = res.unresolved

        report.pruned = store.prune_orphans()
        conn.commit()
        report.stats = store.stats()

    report.duration_ms = int((time.perf_counter() - t0) * 1000)
    return report


@dataclass
class GraphSearchOutcome:
    results: list[SearchResult] = field(default_factory=list)
    expansion: Expansion = field(default_factory=Expansion)
    seeds: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)


def graph_search(
    cfg: Config,
    query: str,
    limit: int | None = None,
    depth: int | None = None,
    filters: SearchFilters | None = None,
) -> GraphSearchOutcome:
    """híbrida -> entidades âncora -> expansão -> chunks -> fusão RRF."""
    limit = limit or cfg.search.limit
    out = GraphSearchOutcome()

    t0 = time.perf_counter()
    base = search(cfg, query, mode="hybrid", limit=max(limit * 2, 20), filters=filters)
    out.timings_ms["search"] = (time.perf_counter() - t0) * 1000
    if not base.results:
        return out

    base_rank = [r.chunk_id for r in base.results]
    by_id = {r.chunk_id: r for r in base.results}

    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)

        t0 = time.perf_counter()
        seeds: dict[str, float] = {}
        ph = ",".join("?" * len(base_rank))
        for row in conn.execute(
            f"""SELECT id, chunk_id, document_id FROM entities
                WHERE chunk_id IN ({ph}) OR document_id IN (
                    SELECT document_id FROM chunks WHERE id IN ({ph})
                )""",
            base_rank + base_rank,
        ):
            anchor_score = 1.0
            if row["chunk_id"] in by_id:
                anchor_score = max(by_id[row["chunk_id"]].score, 0.01)
            seeds[row["id"]] = max(seeds.get(row["id"], 0.0), anchor_score)
        out.seeds = len(seeds)

        limits = TraversalLimits(
            max_depth=depth or cfg.graph.max_depth,
            max_nodes=cfg.graph.max_nodes,
            max_fanout=cfg.graph.max_fanout,
            decay=cfg.graph.decay,
        )
        out.expansion = expand(store, seeds, limits)
        out.timings_ms["graph"] = (time.perf_counter() - t0) * 1000

        # entidades expandidas -> chunks representativos
        expanded = [
            eid for eid, d in out.expansion.depth.items() if d > 0
        ][: cfg.graph.max_nodes]
        chunk_map = store.chunks_for(expanded, limit=2)

        graph_rank: list[str] = []
        reasons: dict[str, str] = {}
        for eid in sorted(expanded, key=lambda e: -out.expansion.scores.get(e, 0.0)):
            for cid in chunk_map.get(eid, []):
                if cid not in graph_rank:
                    graph_rank.append(cid)
                    reasons[cid] = out.expansion.reason.get(eid, "graph")

        t0 = time.perf_counter()
        fused = rrf(
            {"hybrid": base_rank, "graph": graph_rank},
            {"hybrid": 1.0, "graph": 0.7},
            k=cfg.search.rrf_k,
        )
        out.timings_ms["fusion"] = (time.perf_counter() - t0) * 1000

        need = [cid for cid in fused if cid not in by_id]
        if need:
            from ragx.search.service import _hydrate

            for r in _hydrate(conn, [(cid, fused[cid]) for cid in need], {}):
                by_id[r.chunk_id] = r

    results: list[SearchResult] = []
    for cid, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        r = by_id.get(cid)
        if r is None:
            continue
        meta = dict(r.metadata)
        meta["via"] = reasons.get(cid, "hybrid")
        results.append(
            SearchResult(
                chunk_id=r.chunk_id, document_path=r.document_path, kind=r.kind,
                start_line=r.start_line, end_line=r.end_line, score=score,
                content=r.content, project=r.project, symbol=r.symbol,
                heading_path=r.heading_path,
                matched_by=r.matched_by or (reasons.get(cid, "graph"),),
                metadata=meta,
            )
        )

    results = diversify(rerank(query, results), cfg.search.max_per_document)
    out.results = results[:limit]
    return out

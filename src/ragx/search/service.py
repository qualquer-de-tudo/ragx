"""SearchService — orquestra os três modos.

Filtros são aplicados ANTES do top-K em cada motor (predicado no SQL, máscara no
NumPy). Depois seria o modo de falha clássico: filtro restritivo devolve vazio.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ragx.config import Config
from ragx.core.models import ChunkKind, SearchResult
from ragx.embeddings import build_embedder
from ragx.search import keyword
from ragx.search.hybrid import matched_by, rrf
from ragx.search.ranking import diversify, rerank
from ragx.storage.db import open_db
from ragx.storage.vectors import load_index


@dataclass(frozen=True, slots=True)
class SearchFilters:
    lang: str | None = None
    kind: str | None = None
    path_glob: str | None = None
    min_score: float = 0.0


@dataclass
class SearchOutcome:
    results: list[SearchResult] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    mode: str = "hybrid"
    degraded: str | None = None  # motivo, quando o semântico não pôde rodar


def search(
    cfg: Config,
    query: str,
    mode: str | None = None,
    limit: int | None = None,
    filters: SearchFilters | None = None,
    raw: bool = False,
) -> SearchOutcome:
    mode = mode or cfg.search.default_mode
    limit = limit or cfg.search.limit
    filters = filters or SearchFilters()
    candidates = max(limit * cfg.search.candidate_factor, limit)
    out = SearchOutcome(mode=mode)

    with open_db(cfg.db_path, read_only=True) as conn:
        rankings: dict[str, list[str]] = {}
        scores_by_source: dict[str, dict[str, float]] = {}

        if mode in ("keyword", "hybrid"):
            t0 = time.perf_counter()
            kw = keyword.search(
                conn, query, limit=candidates, raw=raw,
                lang=filters.lang, kind=filters.kind, path_glob=filters.path_glob,
            )
            out.timings_ms["keyword"] = (time.perf_counter() - t0) * 1000
            rankings["keyword"] = [cid for cid, _ in kw]
            scores_by_source["keyword"] = dict(kw)

        if mode in ("semantic", "hybrid"):
            t0 = time.perf_counter()
            sem, degraded = _semantic(conn, cfg, query, candidates, filters)
            out.timings_ms["semantic"] = (time.perf_counter() - t0) * 1000
            if degraded:
                out.degraded = degraded
            else:
                rankings["semantic"] = [cid for cid, _ in sem]
                scores_by_source["semantic"] = dict(sem)

        if not rankings:
            return out

        t0 = time.perf_counter()
        if len(rankings) == 1:
            source = next(iter(rankings))
            fused = scores_by_source[source]
        else:
            fused = rrf(
                rankings,
                {
                    "semantic": cfg.search.weight_semantic,
                    "keyword": cfg.search.weight_keyword,
                },
                k=cfg.search.rrf_k,
            )
        out.timings_ms["fusion"] = (time.perf_counter() - t0) * 1000

        sources = matched_by(rankings)
        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[: candidates * 2]
        results = _hydrate(conn, ordered, sources)

    results = rerank(query, results)
    results = diversify(results, cfg.search.max_per_document)
    if filters.min_score > 0:
        results = [r for r in results if r.score >= filters.min_score]
    out.results = results[:limit]
    return out


def _semantic(
    conn: sqlite3.Connection, cfg: Config, query: str, k: int, filters: SearchFilters
) -> tuple[list[tuple[str, float]], str | None]:
    index = load_index(conn)
    if index.size == 0:
        return [], "sem embeddings — rode: ragx index --embed-only"
    try:
        embedder = build_embedder(cfg)
        qvec = embedder.embed_query(query)
    except Exception as exc:  # embedder fora do ar não derruba a busca
        return [], f"embedder indisponível ({type(exc).__name__}) — usando só keyword"

    mask = _filter_mask(conn, index.ids, filters)
    hits = index.search(qvec, k, mask=mask, rescore=cfg.embedding.rescore)
    return hits, None


def _filter_mask(
    conn: sqlite3.Connection, ids: list[str], filters: SearchFilters
) -> np.ndarray | None:
    """Máscara aplicada ANTES do top-K, não depois."""
    if not (filters.lang or filters.kind or filters.path_glob):
        return None
    sql = """SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id WHERE 1=1"""
    args: list[object] = []
    if filters.lang:
        sql += " AND d.lang = ?"
        args.append(filters.lang)
    if filters.kind:
        sql += " AND c.kind = ?"
        args.append(filters.kind)
    if filters.path_glob:
        sql += " AND d.rel_path LIKE ?"
        args.append(filters.path_glob.replace("*", "%"))
    allowed = {r["id"] for r in conn.execute(sql, args)}
    return np.fromiter((cid in allowed for cid in ids), dtype=bool, count=len(ids))


def _hydrate(
    conn: sqlite3.Connection,
    ordered: list[tuple[str, float]],
    sources: dict[str, tuple[str, ...]],
) -> list[SearchResult]:
    if not ordered:
        return []
    ids = [cid for cid, _ in ordered]
    placeholders = ",".join("?" * len(ids))
    rows = {
        r["id"]: dict(r)
        for r in conn.execute(
            f"""SELECT c.*, d.rel_path, d.lang, d.doc_kind, d.redacted
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id IN ({placeholders})""",
            ids,
        )
    }
    out: list[SearchResult] = []
    for cid, score in ordered:
        r = rows.get(cid)
        if r is None:
            continue
        out.append(
            SearchResult(
                chunk_id=cid,
                document_path=r["rel_path"],
                kind=ChunkKind(r["kind"]),
                start_line=r["start_line"],
                end_line=r["end_line"],
                score=score,
                content=r["content"],
                symbol=r["symbol"],
                heading_path=r["heading_path"],
                matched_by=sources.get(cid, ()),
                metadata=_meta(r),
            )
        )
    return out


def _meta(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "lang": r["lang"],
        "doc_kind": r["doc_kind"],
        "token_count": r["token_count"],
        "redacted": bool(r["redacted"]),
        "ordinal": r["ordinal"],
    }

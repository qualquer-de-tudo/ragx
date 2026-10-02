"""SearchService — orquestra os três modos.

Filtros são aplicados ANTES do top-K em cada motor (predicado no SQL, máscara no
NumPy). Depois seria o modo de falha clássico: filtro restritivo devolve vazio.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ragx.config import Config
from ragx.core.models import ChunkKind, SearchResult
from ragx.embeddings import build_embedder, embedder_id
from ragx.search import keyword
from ragx.search.hybrid import matched_by, rrf
from ragx.search.ranking import diversify, rerank
from ragx.storage.db import open_db
from ragx.storage.vectors import load_index
from ragx.tiers import Tier


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
    #: o semântico RODOU, mas nem todo chunk tem vetor (o embedder caiu no meio):
    #: o resultado é válido e incompleto, que é diferente de `degraded`
    partial: str | None = None
    #: o vetor da consulta, quando o semântico rodou: o `build_context` o reaproveita em vez de embutir de novo (RAGX-0150)
    query_vec: np.ndarray | None = field(default=None, repr=False, compare=False)


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
            sem, degraded, partial, out.query_vec = _semantic(conn, cfg, query, candidates, filters)
            out.timings_ms["semantic"] = (time.perf_counter() - t0) * 1000
            out.partial = partial
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
        results = _hydrate(conn, ordered, sources, cfg)

    results = rerank(
        query, results,
        work_weight=cfg.search.weight_tier_work,
        test_weight=cfg.search.weight_tier_test,
    )
    results = diversify(results, cfg.search.max_per_document)
    if filters.min_score > 0:
        results = [r for r in results if r.score >= filters.min_score]
    out.results = results[:limit]
    return out


def _semantic(
    conn: sqlite3.Connection, cfg: Config, query: str, k: int, filters: SearchFilters
) -> tuple[list[tuple[str, float]], str | None, str | None, np.ndarray | None]:
    """(hits, degraded, partial, vetor da consulta). Usa o modelo CONFIGURADO, não o mais recente do banco.

    Antes `load_index(conn)` pegava o último modelo registrado: com outra dimensão
    estourava `ValueError: matmul` (fora do `try` do embedder) e, com a mesma
    dimensão, devolvia resultado aleatório em silêncio (RAGX-0136).
    """
    try:
        wanted = embedder_id(cfg)
    except Exception as exc:
        return [], f"embedder indisponível ({type(exc).__name__}) — usando só keyword", None, None

    index = load_index(conn, wanted)
    if index.size == 0:
        outros = conn.execute(
            "SELECT model_id, COUNT(*) AS n FROM embeddings GROUP BY model_id"
        ).fetchall()
        if not outros:
            return [], "sem embeddings — rode: ragx index --embed-only", None, None
        quais = ", ".join(f"{r['model_id']} ({r['n']} vetores)" for r in outros)
        return [], (
            f"o índice vetorial é de {quais}, mas a configuração pede {wanted} — "
            "usando só keyword; rode: ragx index --embed-only"
        ), None, None
    try:
        embedder = build_embedder(cfg)
        qvec = embedder.embed_query(query)
    except Exception as exc:  # embedder fora do ar não derruba a busca
        return [], f"embedder indisponível ({type(exc).__name__}) — usando só keyword", None, None

    precisa = index.dim if (index.has_full and cfg.embedding.rescore) else index.versioned_dim
    if qvec.size < precisa:
        return [], (
            f"o embedder devolveu {qvec.size} dimensões e o índice de {wanted} pede {precisa} — "
            "usando só keyword"
        ), None, None

    mask = _filter_mask(conn, index.ids, filters)
    hits = index.search(qvec, k, mask=mask, rescore=cfg.embedding.rescore)
    total = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    avisos = []
    if index.size < total:
        avisos.append(f"vetores parciais: {index.size} de {total} chunks — rode: ragx index --embed-only")
    if not index.has_full:
        # só o int8 versionado (um clone depois de `ragx sync`): a busca roda, com menos precisão
        sem_float = int(conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE model_id = ? AND vector IS NULL", (wanted,)
        ).fetchone()[0])
        if sem_float:
            avisos.append(
                f"vetores só grosseiros (int8@{index.versioned_dim}): {sem_float} chunks sem float32 "
                "— rode: ragx index --embed-only"
            )
    return hits, None, "; ".join(avisos) or None, qvec


def _filter_mask(
    conn: sqlite3.Connection, ids: list[str], filters: SearchFilters
) -> np.ndarray | None:
    """Máscara aplicada ANTES do top-K, não depois."""
    if not (filters.lang or filters.kind or filters.path_glob):
        return None
    sql, args = _filtro_sql(filters)
    allowed = {r["id"] for r in conn.execute(sql, args)}
    return np.fromiter((cid in allowed for cid in ids), dtype=bool, count=len(ids))


def _filtro_sql(filters: SearchFilters) -> tuple[str, list[object]]:
    """O predicado de `SearchFilters` em SQL. Uma só definição: máscara da busca e grafo usam esta."""
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
    return sql, args


def filter_chunk_ids(
    conn: sqlite3.Connection, ids: Iterable[str], filters: SearchFilters | None
) -> set[str]:
    """Quais dos `ids` passam em `filters`, com a MESMA semântica de `_filter_mask`.

    Reusa o SQL (`LIKE` ignora maiúsculas em ASCII, `fnmatch` do Python não), em vez de
    reimplementar o filtro em Python. Sem filtro, devolve todos.
    """
    pedidos = list(dict.fromkeys(ids))
    if filters is None or not (filters.lang or filters.kind or filters.path_glob):
        return set(pedidos)
    base, args = _filtro_sql(filters)
    ok: set[str] = set()
    for inicio in range(0, len(pedidos), 400):  # abaixo do limite de variáveis do SQLite
        lote = pedidos[inicio : inicio + 400]
        ph = ",".join("?" * len(lote))
        ok.update(r["id"] for r in conn.execute(f"{base} AND c.id IN ({ph})", [*args, *lote]))
    return ok


def _hydrate(
    conn: sqlite3.Connection,
    ordered: list[tuple[str, float]],
    sources: dict[str, tuple[str, ...]],
    cfg: Config | None = None,
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
                metadata=_meta(r, cfg),
            )
        )
    return out


def _meta(r: dict[str, Any], cfg: Config | None = None) -> dict[str, Any]:
    return {
        "lang": r["lang"],
        "doc_kind": r["doc_kind"],
        "token_count": r["token_count"],
        "redacted": bool(r["redacted"]),
        "ordinal": r["ordinal"],
        # A camada é calculada na leitura, não lida do banco: mudar
        # `work_paths` no `ragx.toml` passa a valer sem reindexar.
        "tier": _tier(r["rel_path"], cfg).value,
    }


def _tier(rel_path: str, cfg: Config | None) -> Tier:
    from ragx.tiers import DEFAULT_TEST, DEFAULT_WORK, classify

    if cfg is None:
        return classify(rel_path)
    work = cfg.index.work_paths
    test = cfg.index.test_paths
    return classify(
        rel_path,
        work=tuple(work) if work is not None else DEFAULT_WORK,
        test=tuple(test) if test is not None else DEFAULT_TEST,
    )

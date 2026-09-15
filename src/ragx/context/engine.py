"""ContextEngine — busca → grafo → ranking → dedup → compressão → orçamento.

Entrega um ContextPack: texto pronto para colar num prompt, DENTRO de um
orçamento, com toda fonte preservada.

Ver docs/07-context-engine.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ragx.config import Config
from ragx.context import compress as compressor
from ragx.context.budget import allocate
from ragx.context.dedup import dedupe_literal, dedupe_near, mmr
from ragx.core.models import SearchResult
from ragx.embeddings import build_embedder
from ragx.embeddings.base import dequantize, l2_normalize, unpack_f32
from ragx.search.service import SearchFilters, search
from ragx.storage.db import open_db
from ragx.tokens import count_tokens

INTENTS_PATH = Path(__file__).parent / "intents.yaml"


@dataclass(frozen=True, slots=True)
class ContextFragment:
    document_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    tokens: int
    compressed: bool
    reason: str
    project: str = "current"
    symbol: str | None = None
    heading_path: str | None = None
    strategy: str = "none"


@dataclass
class ContextPack:
    query: str
    fragments: tuple[ContextFragment, ...] = ()
    estimated_tokens: int = 0
    budget: int = 0
    sources: tuple[str, ...] = ()
    dropped: tuple[tuple[str, str], ...] = ()
    intent: str = "general"
    stats: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


@lru_cache(maxsize=1)
def _intents() -> dict[str, Any]:
    data = yaml.safe_load(INTENTS_PATH.read_text(encoding="utf-8"))
    for item in data["intents"]:
        item["_re"] = [re.compile(p, re.IGNORECASE) for p in item["patterns"]]
    return data


def detect_intent(query: str) -> dict[str, Any]:
    data = _intents()
    for item in data["intents"]:
        if any(rx.search(query) for rx in item["_re"]):
            return item
    return data["default"]


def build_context(
    cfg: Config,
    query: str,
    budget: int | None = None,
    include_graph: bool = True,
    depth: int | None = None,
    filters: SearchFilters | None = None,
    use_cache: bool = True,
) -> ContextPack:
    budget = budget or cfg.context.default_tokens
    intent = detect_intent(query)
    pack = ContextPack(query=query, budget=budget, intent=str(intent["id"]))
    t_start = time.perf_counter()

    cache_key = _cache_key(cfg, query, budget, include_graph, depth)
    if use_cache:
        hit = _cache_read(cfg, cache_key)
        if hit is not None:
            hit.cached = True
            return hit

    # [1] recuperação
    t0 = time.perf_counter()
    candidates, expansion_stats = _retrieve(cfg, query, include_graph, depth, intent, filters)
    t_retrieve = (time.perf_counter() - t0) * 1000
    if not candidates:
        pack.stats = {"retrieve_ms": round(t_retrieve, 2), "candidates": 0}
        return pack

    raw_tokens = sum(_tok(c) for c in candidates)
    dropped: list[tuple[str, str]] = []

    # [2] ranking por intenção
    candidates = _apply_intent(candidates, intent)

    # [3] dedup
    t0 = time.perf_counter()
    lit = dedupe_literal(candidates)
    dropped.extend((r.chunk_id, why) for r, why in lit.dropped)

    vectors, query_vec = _vectors_for(cfg, [r.chunk_id for r in lit.kept], query)
    near = dedupe_near(lit.kept, vectors, cfg.context.dedup_threshold)
    dropped.extend((r.chunk_id, why) for r, why in near.dropped)

    keep_n = max(cfg.search.limit * 3, 20)
    div = mmr(near.kept, vectors, query_vec, cfg.context.mmr_lambda, k=keep_n)
    dropped.extend((r.chunk_id, why) for r, why in div.dropped)
    t_dedup = (time.perf_counter() - t0) * 1000

    # [4] orçamento
    plan = allocate(
        div.kept, budget,
        reserve_ratio=cfg.context.reserve_ratio,
        min_sources=cfg.context.min_sources,
    )
    dropped.extend((r.chunk_id, why) for r, why in plan.dropped)

    # [5] compressão — só se ainda não couber
    t0 = time.perf_counter()
    selected = plan.selected
    if not selected and div.kept:
        # Nada coube: o melhor candidato sozinho já passa do orçamento. Devolver
        # vazio seria pior que devolver o trecho comprimido — o agente perderia
        # a única fonte relevante.
        selected = (div.kept[0],)
        dropped = [d for d in dropped if d[0] != div.kept[0].chunk_id]
    fragments = _to_fragments(selected, query, budget, cfg, force_compress=not plan.selected)
    t_compress = (time.perf_counter() - t0) * 1000

    total = sum(f.tokens for f in fragments)
    # Garantia dura: o pack fecha ABAIXO do teto, sempre.
    while total > budget and fragments:
        removed = fragments[-1]
        fragments = fragments[:-1]
        dropped.append((f"{removed.document_path}:{removed.start_line}", "budget:overflow"))
        total = sum(f.tokens for f in fragments)

    pack.fragments = tuple(fragments)
    pack.estimated_tokens = total
    pack.sources = tuple(dict.fromkeys(f.document_path for f in fragments))
    pack.dropped = tuple(dropped)
    pack.stats = {
        "candidates": len(candidates),
        "raw_tokens": raw_tokens,
        "kept": len(fragments),
        "compressed": sum(1 for f in fragments if f.compressed),
        "retrieve_ms": round(t_retrieve, 2),
        "dedup_ms": round(t_dedup, 2),
        "compress_ms": round(t_compress, 2),
        "total_ms": round((time.perf_counter() - t_start) * 1000, 2),
        **expansion_stats,
    }

    if use_cache:
        _cache_write(cfg, cache_key, pack)
    return pack


# ── etapas ──────────────────────────────────────────────────────────────
def _retrieve(
    cfg: Config,
    query: str,
    include_graph: bool,
    depth: int | None,
    intent: dict[str, Any],
    filters: SearchFilters | None,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Pede bem mais do que cabe: o funil seguinte precisa ter o que descartar."""
    want = max(cfg.search.limit * 5, 25)
    if include_graph and cfg.graph.enabled:
        from ragx.graph.service import graph_search

        out = graph_search(
            cfg, query, limit=want, depth=depth or int(intent.get("graph_depth", 1)),
            filters=filters,
        )
        if out.results:
            return list(out.results), {
                "graph_seeds": out.seeds,
                "graph_nodes": len(out.expansion.scores),
                "graph_truncated": out.expansion.truncated,
            }
    res = search(cfg, query, mode="hybrid", limit=want, filters=filters)
    return list(res.results), {"graph_seeds": 0, "graph_nodes": 0}


def _apply_intent(results: list[SearchResult], intent: dict[str, Any]) -> list[SearchResult]:
    weights: dict[str, float] = intent.get("weights", {})
    if not weights:
        return results
    out = []
    for r in results:
        kind = str(r.metadata.get("doc_kind", "doc"))
        factor = weights.get(kind, 1.0)
        out.append(_rescore(r, r.score * factor))
    return sorted(out, key=lambda r: -r.score)


def _to_fragments(
    selected: tuple[SearchResult, ...], query: str, budget: int, cfg: Config,
    force_compress: bool = False,
) -> list[ContextFragment]:
    if not selected:
        return []
    frags: list[ContextFragment] = []
    usable = int(budget * (1.0 - cfg.context.reserve_ratio))
    natural = sum(count_tokens(r.content) for r in selected)

    # `allocate` já escolheu um conjunto que cabe. Comprimir por padrão depois
    # disso só desperdiça orçamento — o agente receberia menos contexto do que
    # poderia. Só comprime quando o conjunto REALMENTE excede.
    needs_compression = cfg.context.compress and (natural > usable or force_compress)
    total_score = sum(max(r.score, 1e-6) for r in selected)

    for r in selected:
        is_code = str(r.metadata.get("doc_kind")) == "code"
        if needs_compression:
            # Alvo proporcional ao score: os melhores ficam mais inteiros.
            share = max(r.score, 1e-6) / total_score
            target = max(int(usable * share), 48)
            c = compressor.compress(r.content, target, query=query, is_code=is_code)
        else:
            c = compressor.Compressed(r.content, False, "none", 0)
        frags.append(
            ContextFragment(
                document_path=r.document_path,
                start_line=r.start_line,
                end_line=r.end_line,
                content=c.text,
                score=r.score,
                tokens=count_tokens(c.text),
                compressed=c.compressed,
                strategy=c.strategy,
                reason=str(r.metadata.get("via") or (r.matched_by[0] if r.matched_by else "hybrid")),
                project=r.project,
                symbol=r.symbol,
                heading_path=r.heading_path,
            )
        )
    return frags


def _vectors_for(
    cfg: Config, chunk_ids: list[str], query: str
) -> tuple[dict[str, np.ndarray], np.ndarray | None]:
    """Reaproveita os vetores JÁ gravados — dedup não re-embarca nada."""
    if not chunk_ids:
        return {}, None
    vectors: dict[str, np.ndarray] = {}
    with open_db(cfg.db_path, read_only=True) as conn:
        # Vetores de modelos distintos NÃO são comparáveis — e um banco que já
        # trocou de provider guarda os dois. Sem este filtro, o produto escalar
        # recebe dimensões diferentes e estoura.
        active = conn.execute(
            "SELECT id FROM embedding_models ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if active is None:
            return {}, None
        ph = ",".join("?" * len(chunk_ids))
        for r in conn.execute(
            f"""SELECT chunk_id, vector, vector_q, q_scale, q_offset
                FROM embeddings WHERE model_id = ? AND chunk_id IN ({ph})""",
            [active["id"], *chunk_ids],
        ):
            if r["vector"] is not None:
                vectors[r["chunk_id"]] = l2_normalize(unpack_f32(r["vector"]))
            else:
                vectors[r["chunk_id"]] = l2_normalize(
                    dequantize(r["vector_q"], r["q_scale"], r["q_offset"])
                )
    if not vectors:
        return {}, None

    dim = len(next(iter(vectors.values())))
    try:
        qv = l2_normalize(build_embedder(cfg).embed_query(query)[:dim])
    except Exception:
        return vectors, None
    return vectors, qv


def _rescore(r: SearchResult, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=r.chunk_id, document_path=r.document_path, kind=r.kind,
        start_line=r.start_line, end_line=r.end_line, score=score, content=r.content,
        project=r.project, symbol=r.symbol, heading_path=r.heading_path,
        matched_by=r.matched_by, metadata=r.metadata,
    )


def _tok(r: SearchResult) -> int:
    n = r.metadata.get("token_count")
    return n if isinstance(n, int) and n > 0 else count_tokens(r.content)


# ── cache ───────────────────────────────────────────────────────────────
def _cache_key(
    cfg: Config, query: str, budget: int, include_graph: bool, depth: int | None
) -> str:
    fingerprint = json.dumps(
        {
            "q": query, "b": budget, "g": include_graph, "d": depth,
            "dedup": cfg.context.dedup_threshold, "mmr": cfg.context.mmr_lambda,
            "compress": cfg.context.compress, "model": cfg.embedding.model,
            "db": _db_version(cfg),
        },
        sort_keys=True,
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]


def _db_version(cfg: Config) -> str:
    """O id do último run invalida o cache assim que o índice muda."""
    if not cfg.db_path.exists():
        return "0"
    try:
        with open_db(cfg.db_path, read_only=True) as conn:
            row = conn.execute("SELECT MAX(id) AS v FROM index_runs").fetchone()
            return str(row["v"] if row and row["v"] else 0)
    except Exception:
        return "0"


def _cache_dir(cfg: Config) -> Path:
    return cfg.state_dir / "cache" / "context"


def _cache_read(cfg: Config, key: str) -> ContextPack | None:
    path = _cache_dir(cfg) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return ContextPack(
        query=data["query"],
        fragments=tuple(ContextFragment(**f) for f in data["fragments"]),
        estimated_tokens=data["estimated_tokens"],
        budget=data["budget"],
        sources=tuple(data["sources"]),
        dropped=tuple(tuple(d) for d in data["dropped"]),  # type: ignore[misc]
        intent=data.get("intent", "general"),
        stats=data.get("stats", {}),
    )


def _cache_write(cfg: Config, key: str, pack: ContextPack) -> None:
    path = _cache_dir(cfg) / f"{key}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "query": pack.query,
                    "fragments": [f.__dict__ if hasattr(f, "__dict__") else _asdict(f)
                                  for f in pack.fragments],
                    "estimated_tokens": pack.estimated_tokens,
                    "budget": pack.budget,
                    "sources": list(pack.sources),
                    "dropped": [list(d) for d in pack.dropped],
                    "intent": pack.intent,
                    "stats": pack.stats,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass  # cache é otimização, nunca motivo de falha


def _asdict(f: ContextFragment) -> dict[str, Any]:
    return {s: getattr(f, s) for s in ContextFragment.__slots__}

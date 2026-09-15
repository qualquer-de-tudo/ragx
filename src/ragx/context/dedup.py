"""Deduplicação em três níveis.

  1. duplicata literal      mesmo content_hash
  2. quase-duplicata        cosseno acima do limiar, sobre vetores já gravados
  3. redundância            MMR: troca um pouco de relevância por cobertura

Ver docs/07-context-engine.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ragx.core.models import SearchResult


@dataclass(frozen=True, slots=True)
class DedupResult:
    kept: tuple[SearchResult, ...]
    dropped: tuple[tuple[SearchResult, str], ...]


def dedupe_literal(results: Sequence[SearchResult]) -> DedupResult:
    """Código copiado em dois arquivos aparece uma vez — o de maior score."""
    seen: dict[str, SearchResult] = {}
    kept: list[SearchResult] = []
    dropped: list[tuple[SearchResult, str]] = []
    for r in results:
        h = str(r.metadata.get("content_hash") or r.content)
        prev = seen.get(h)
        if prev is None:
            seen[h] = r
            kept.append(r)
        else:
            dropped.append((r, f"duplicate_of:{prev.document_path}"))
    return DedupResult(tuple(kept), tuple(dropped))


def dedupe_near(
    results: Sequence[SearchResult],
    vectors: dict[str, np.ndarray],
    threshold: float = 0.93,
) -> DedupResult:
    """Trechos que dizem a mesma coisa com palavras diferentes."""
    kept: list[SearchResult] = []
    dropped: list[tuple[SearchResult, str]] = []
    kept_vecs: list[tuple[str, np.ndarray]] = []

    for r in results:
        v = vectors.get(r.chunk_id)
        if v is None:
            kept.append(r)
            continue
        collision = next(
            (path for path, kv in kept_vecs if float(kv @ v) >= threshold), None
        )
        if collision is not None:
            dropped.append((r, f"near_duplicate_of:{collision}"))
            continue
        kept.append(r)
        kept_vecs.append((r.document_path, v))
    return DedupResult(tuple(kept), tuple(dropped))


def mmr(
    results: Sequence[SearchResult],
    vectors: dict[str, np.ndarray],
    query_vec: np.ndarray | None,
    lambda_: float = 0.7,
    k: int = 20,
) -> DedupResult:
    """Maximal Marginal Relevance: relevância menos redundância.

    `lambda_` alto favorece relevância; baixo favorece cobertura.
    """
    if query_vec is None or not vectors or k <= 0:
        return DedupResult(tuple(results[:k]) if k else tuple(results), ())

    pool = list(results)
    selected: list[SearchResult] = []
    sel_vecs: list[np.ndarray] = []

    while pool and len(selected) < k:
        best: SearchResult | None = None
        best_value = float("-inf")
        for cand in pool:
            v = vectors.get(cand.chunk_id)
            relevance = float(v @ query_vec) if v is not None else cand.score
            redundancy = (
                max((float(v @ s) for s in sel_vecs), default=0.0)
                if v is not None
                else 0.0
            )
            value = lambda_ * relevance - (1.0 - lambda_) * redundancy
            if value > best_value:
                best_value, best = value, cand
        if best is None:
            break
        selected.append(best)
        bv = vectors.get(best.chunk_id)
        if bv is not None:
            sel_vecs.append(bv)
        pool.remove(best)

    return DedupResult(tuple(selected), tuple((r, "mmr") for r in pool))

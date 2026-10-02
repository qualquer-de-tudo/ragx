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

    # Vetorizado (RAGX-0150): a relevância é `V @ q` e a redundância vive num vetor `max_sim`, atualizado com
    # `np.maximum(max_sim, V @ V[melhor])` a cada escolha. Semântica idêntica à do laço duplo de antes:
    # candidato SEM vetor usa `cand.score` como relevância e redundância 0,0; sem nenhum escolhido ainda a
    # redundância é 0,0; empate vai para o PRIMEIRO da ordem original (`np.argmax` devolve a primeira ocorrência).
    pool = list(results)
    n = len(pool)
    tem = np.array([r.chunk_id in vectors for r in pool], dtype=bool)
    if tem.any():
        amostra = next(iter(vectors.values()))
        mat = np.zeros((n, len(amostra)), dtype=amostra.dtype)
        for i, r in enumerate(pool):
            if tem[i]:
                mat[i] = vectors[r.chunk_id]
        relevance = np.where(tem, (mat @ query_vec).astype(np.float64), 0.0)
    else:
        mat = np.zeros((n, 0), dtype=np.float32)
        relevance = np.zeros(n, dtype=np.float64)
    relevance = np.where(tem, relevance, np.array([r.score for r in pool], dtype=np.float64))
    max_sim = np.zeros(n, dtype=np.float64)
    ativo = np.ones(n, dtype=bool)
    escolhidos: list[int] = []
    escolheu_vetor = False

    while ativo.any() and len(escolhidos) < k:
        redund = np.where(tem, max_sim, 0.0) if escolheu_vetor else np.zeros(n)
        valor = np.where(ativo, lambda_ * relevance - (1.0 - lambda_) * redund, -np.inf)
        melhor = int(np.argmax(valor))
        escolhidos.append(melhor)
        ativo[melhor] = False
        if tem[melhor]:
            max_sim = np.maximum(max_sim, (mat @ mat[melhor]).astype(np.float64)) if escolheu_vetor else (mat @ mat[melhor]).astype(np.float64)
            escolheu_vetor = True

    selected = [pool[i] for i in escolhidos]
    pool = [pool[i] for i in range(n) if ativo[i]]

    return DedupResult(tuple(selected), tuple((r, "mmr") for r in pool))

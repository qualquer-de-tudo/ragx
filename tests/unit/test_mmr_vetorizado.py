"""MMR vetorizado = o laço duplo de antes (RAGX-0150)."""

from __future__ import annotations

import time
from collections.abc import Sequence

import numpy as np
import pytest

from ragx.context.dedup import DedupResult, mmr
from ragx.core.models import ChunkKind, SearchResult

pytestmark = pytest.mark.unit


def _mmr_antigo(
    results: Sequence[SearchResult], vectors: dict[str, np.ndarray], query_vec: np.ndarray | None,
    lambda_: float = 0.7, k: int = 20,
) -> DedupResult:
    """Cópia da implementação de ANTES da RAGX-0150 (laço duplo), a referência da equivalência."""
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
            redundancy = max((float(v @ s) for s in sel_vecs), default=0.0) if v is not None else 0.0
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


def _res(i: int, score: float) -> SearchResult:
    return SearchResult(chunk_id=f"c{i}", document_path=f"d{i}.py", kind=ChunkKind.FUNCTION, start_line=1, end_line=2,
                        score=score, content="x")


def _unit(rng: np.random.Generator, dim: int) -> np.ndarray:
    v = rng.normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _caso(seed: int, n: int = 30, dim: int = 16, sem_vetor: float = 0.0, repetidos: bool = False):  # type: ignore[no-untyped-def]
    rng = np.random.default_rng(seed)
    results = [_res(i, float(rng.random())) for i in range(n)]
    vectors = {r.chunk_id: _unit(rng, dim) for r in results if rng.random() >= sem_vetor}
    if repetidos and len(vectors) > 4:
        ids = list(vectors)
        for j in range(1, 5):
            vectors[ids[j]] = vectors[ids[0]].copy()  # empates exatos
    return results, vectors, _unit(rng, dim)


def _ids(r: DedupResult) -> tuple[list[str], list[str]]:
    return [x.chunk_id for x in r.kept], [x.chunk_id for x, _ in r.dropped]


@pytest.mark.parametrize("seed", range(200))
def test_mesma_selecao_e_mesma_ordem_em_200_sementes(seed: int) -> None:
    results, vectors, q = _caso(seed, sem_vetor=0.25 if seed % 3 == 0 else 0.0, repetidos=seed % 5 == 0)
    k = [5, 12, 20, 40][seed % 4]
    assert _ids(mmr(results, vectors, q, 0.7, k)) == _ids(_mmr_antigo(results, vectors, q, 0.7, k))


@pytest.mark.parametrize("lam", [0.0, 0.3, 1.0])
def test_lambdas_extremos(lam: float) -> None:
    results, vectors, q = _caso(7)
    assert _ids(mmr(results, vectors, q, lam, 10)) == _ids(_mmr_antigo(results, vectors, q, lam, 10))


def test_k_maior_que_o_conjunto_e_query_vec_ausente() -> None:
    results, vectors, q = _caso(3, n=6)
    assert _ids(mmr(results, vectors, q, 0.7, 50)) == _ids(_mmr_antigo(results, vectors, q, 0.7, 50))
    assert _ids(mmr(results, vectors, None, 0.7, 4)) == _ids(_mmr_antigo(results, vectors, None, 0.7, 4))
    assert _ids(mmr(results, {}, q, 0.7, 4)) == _ids(_mmr_antigo(results, {}, q, 0.7, 4))
    assert _ids(mmr([], vectors, q, 0.7, 4)) == _ids(_mmr_antigo([], vectors, q, 0.7, 4))


def test_so_candidatos_sem_vetor_usa_o_score() -> None:
    results = [_res(i, s) for i, s in enumerate([0.1, 0.9, 0.5])]
    vectors = {"fora": np.ones(4, dtype=np.float32)}
    q = np.ones(4, dtype=np.float32)
    assert _ids(mmr(results, vectors, q, 0.7, 3)) == _ids(_mmr_antigo(results, vectors, q, 0.7, 3))


def test_30_candidatos_em_poucos_ms() -> None:
    results, vectors, q = _caso(1, n=30, dim=128)
    t0 = time.perf_counter()
    for _ in range(20):
        mmr(results, vectors, q, 0.7, 30)
    novo = (time.perf_counter() - t0) / 20 * 1000
    t0 = time.perf_counter()
    for _ in range(20):
        _mmr_antigo(results, vectors, q, 0.7, 30)
    antigo = (time.perf_counter() - t0) / 20 * 1000
    print(f"[0150] mmr 30 candidatos: antigo {antigo:.2f} ms, novo {novo:.2f} ms")
    assert novo < antigo

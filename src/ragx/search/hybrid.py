"""Fusão híbrida por RRF.

Cosseno vive em [-1,1] e BM25 é ilimitado e dependente do corpus. Normalizar os
dois exigiria calibração por projeto; RRF usa só a POSIÇÃO e dispensa tuning.
"""

from __future__ import annotations

from collections import defaultdict

RRF_K = 60


def rrf(
    rankings: dict[str, list[str]], weights: dict[str, float] | None = None, k: int = RRF_K
) -> dict[str, float]:
    weights = weights or {}
    scores: dict[str, float] = defaultdict(float)
    for source, ranked_ids in rankings.items():
        w = weights.get(source, 1.0)
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] += w / (k + rank)
    return dict(scores)


def matched_by(rankings: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = defaultdict(list)
    for source, ids in rankings.items():
        for cid in ids:
            out[cid].append(source)
    return {cid: tuple(sorted(srcs)) for cid, srcs in out.items()}

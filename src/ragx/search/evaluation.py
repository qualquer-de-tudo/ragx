"""Avaliação de qualidade de recuperação.

Mede o que o RAGX de fato controla — recuperação, não geração. É o que impede
"melhorei a busca" virar opinião. Ver docs/05-busca.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ragx.config import Config
from ragx.core.errors import UsageError
from ragx.search.service import search

MODES = ("keyword", "semantic", "hybrid")


@dataclass(frozen=True, slots=True)
class EvalCase:
    query: str
    relevant_paths: tuple[str, ...]
    note: str = ""


@dataclass
class ModeMetrics:
    mode: str
    recall_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    cases: int = 0
    failures: list[tuple[str, int | None]] = field(default_factory=list)


def load_cases(path: Path) -> list[EvalCase]:
    if not path.is_file():
        raise UsageError(f"conjunto de avaliação não encontrado: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    cases = [
        EvalCase(
            query=item["query"],
            relevant_paths=tuple(item.get("relevant_paths", [])),
            note=item.get("note", ""),
        )
        for item in raw
    ]
    if not cases:
        raise UsageError(f"conjunto de avaliação vazio: {path}")
    return cases


def _first_hit_rank(paths: list[str], relevant: tuple[str, ...]) -> int | None:
    for i, p in enumerate(paths, start=1):
        if p in relevant:
            return i
    return None


def _ndcg(paths: list[str], relevant: tuple[str, ...], k: int = 10) -> float:
    gains = [1.0 if p in relevant else 0.0 for p in paths[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def evaluate(
    cfg: Config, cases: list[EvalCase], modes: tuple[str, ...] = MODES
) -> list[ModeMetrics]:
    out: list[ModeMetrics] = []
    for mode in modes:
        m = ModeMetrics(mode=mode, cases=len(cases))
        recall = mrr = ndcg = 0.0
        for case in cases:
            res = search(cfg, case.query, mode=mode, limit=10)
            paths = [r.document_path for r in res.results]
            top5 = set(paths[:5])
            if any(p in top5 for p in case.relevant_paths):
                recall += 1.0
            rank = _first_hit_rank(paths, case.relevant_paths)
            if rank:
                mrr += 1.0 / rank
            if rank is None or rank > 5:
                m.failures.append((case.query, rank))
            ndcg += _ndcg(paths, case.relevant_paths)
        n = max(len(cases), 1)
        m.recall_at_5 = recall / n
        m.mrr = mrr / n
        m.ndcg_at_10 = ndcg / n
        out.append(m)
    return out

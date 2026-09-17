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


#: Acima desta largura, o conjunto de consultas não distingue os modos, e
#: comparar duas medições é ler ruído. Com n=26 a largura é ~0,33.
MAX_CI_WIDTH = 0.20


@dataclass
class ModeMetrics:
    mode: str
    recall_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    cases: int = 0
    failures: list[tuple[str, int | None]] = field(default_factory=list)
    #: Intervalo de confiança de 95% do recall@5.
    recall_ci: tuple[float, float] = (0.0, 0.0)

    @property
    def ci_width(self) -> float:
        return self.recall_ci[1] - self.recall_ci[0]

    @property
    def conclusive(self) -> bool:
        """`False` quando o conjunto é pequeno demais para o número significar algo."""
        return self.ci_width <= MAX_CI_WIDTH


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confiança de Wilson para uma proporção.

    Wilson e não o normal: com n pequeno e proporção perto de 0 ou 1, o
    intervalo normal escapa de [0,1] e mente sobre a precisão. Foi com n=26 que
    "0,62 contra 0,77" virou a afirmação publicada de que a busca híbrida
    falhou o critério — quando os dois intervalos se sobrepõem em quase toda a
    extensão.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = hits / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centro - meio), min(1.0, centro + meio))


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
    """nDCG@k medido em DOCUMENTOS distintos.

    O ganho é contado uma vez por documento relevante, na posição em que ele
    aparece PELA PRIMEIRA VEZ. A lista de entrada é de chunks, e vários chunks
    do mesmo arquivo são comuns — contá-los como acertos separados era um bug
    com direção: premiava devolver o mesmo arquivo picado em pedaços, que é o
    oposto de um contexto bom.

    Além de premiar o errado, quebrava a escala. O denominador ideal sempre foi
    contado em arquivos; com o numerador em chunks, o resultado passava de 1,0
    — `_ndcg(['a','a','a'], ('a',))` devolvia **2,131** numa métrica cuja
    definição tem teto 1,0.

    Ver `task/fase-14-evolucao-do-rag/RAGX-0098-*.md`.
    """
    vistos: set[str] = set()
    dcg = 0.0
    for i, p in enumerate(paths[:k]):
        if p in relevant and p not in vistos:
            vistos.add(p)
            dcg += 1.0 / math.log2(i + 2)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(set(relevant)), k)))
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
        m.recall_ci = wilson_ci(int(recall), n)
        out.append(m)
    return out

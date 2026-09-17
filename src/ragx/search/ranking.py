"""Reranking determinístico e diversidade de fonte (docs/05-busca.md).

Sem modelo extra no MVP: os sinais são declarados, auditáveis e testáveis.
Cross-encoder fica registrado como evolução pós-MVP.
"""

from __future__ import annotations

import re

from ragx.core.models import DocKind, SearchResult
from ragx.tiers import Tier

_QUESTION = re.compile(
    r"\?|^\s*(como|o que|oque|por que|porque|quando|onde|qual|quais|quem)\b", re.IGNORECASE
)
_IDENTIFIER = re.compile(r"[a-z][A-Z]|::|\(\)|_[a-z]|\.[a-z]+\(")


def looks_like_question(query: str) -> bool:
    return bool(_QUESTION.search(query))


def looks_like_identifier(query: str) -> bool:
    return bool(_IDENTIFIER.search(query))


def rerank(
    query: str,
    results: list[SearchResult],
    work_weight: float = 1.0,
    test_weight: float = 1.0,
) -> list[SearchResult]:
    """Ajustes determinísticos sobre o score fundido.

    `work_weight`/`test_weight` pesam a CAMADA do documento (`ragx.tiers`):
    um plano de tarefa fala do mesmo assunto que a documentação, com o mesmo
    vocabulário, e sem a resposta. Os defaults de 1,0 mantêm o comportamento
    antigo para quem chama sem os parâmetros.
    """
    is_question = looks_like_question(query)
    is_ident = looks_like_identifier(query)
    q_low = query.lower().strip()

    boosted: list[SearchResult] = []
    for r in results:
        factor = 1.0
        if r.symbol and (r.symbol.lower() == q_low or r.symbol.lower().endswith("." + q_low)):
            factor *= 1.5
        kind = r.metadata.get("doc_kind")
        if is_question and kind == DocKind.DOC.value:
            factor *= 1.2
        if is_ident and kind == DocKind.CODE.value:
            factor *= 1.2
        if r.metadata.get("token_count", 999) < 32:
            factor *= 0.8
        if r.metadata.get("redacted"):
            factor *= 0.9
        tier = r.metadata.get("tier")
        if tier == Tier.WORK.value:
            factor *= work_weight
        elif tier == Tier.TEST.value:
            factor *= test_weight
        boosted.append(_with_score(r, r.score * factor))
    return sorted(boosted, key=lambda r: -r.score)


def diversify(results: list[SearchResult], max_per_document: int = 3) -> list[SearchResult]:
    """Evita 10 métodos do mesmo arquivo no topo. Os excedentes descem, não somem."""
    kept: list[SearchResult] = []
    overflow: list[SearchResult] = []
    seen: dict[str, int] = {}
    for r in results:
        n = seen.get(r.document_path, 0)
        if n < max_per_document:
            seen[r.document_path] = n + 1
            kept.append(r)
        else:
            overflow.append(r)
    return kept + overflow


def _with_score(r: SearchResult, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=r.chunk_id, document_path=r.document_path, kind=r.kind,
        start_line=r.start_line, end_line=r.end_line, score=score, content=r.content,
        project=r.project, symbol=r.symbol, heading_path=r.heading_path,
        matched_by=r.matched_by, metadata=r.metadata,
    )

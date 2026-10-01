"""Alocação de orçamento de tokens.

Knapsack aproximado por densidade de valor, com reservas fixas. A reserva por
fonte existe para evitar o modo de falha clássico: 3.000 tokens todos vindos de
um único arquivo, sem a documentação que explica o porquê.

Ver docs/07-context-engine.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ragx.context import format as fmt_mod
from ragx.core.models import SearchResult
from ragx.tokens import count_tokens

# Margem sobre o orçamento: a contagem é estimativa declarada, então o pack
# sempre fecha abaixo do teto, nunca em cima dele.
SAFETY_MARGIN = 0.03


@dataclass(frozen=True, slots=True)
class BudgetPlan:
    selected: tuple[SearchResult, ...]
    dropped: tuple[tuple[SearchResult, str], ...]
    used_tokens: int
    budget: int
    overhead: int


def allocate(
    candidates: Sequence[SearchResult],
    budget: int,
    reserve_ratio: float = 0.05,
    min_sources: int = 3,
    per_fragment_overhead: int | None = None,
) -> BudgetPlan:
    """Seleciona fragmentos por densidade `score / tokens`, com reserva por fonte.

    O custo de cada fragmento inclui o seu cabeçalho REAL (`## [i] caminho:linhas ›
    nome`) e o rodapé é reservado uma vez; `per_fragment_overhead` fixo só existe
    para quem quer o comportamento antigo (RAGX-0154).
    """
    if budget <= 0 or not candidates:
        return BudgetPlan((), tuple((c, "budget") for c in candidates), 0, budget, 0)

    usable = int(budget * (1.0 - reserve_ratio - SAFETY_MARGIN))
    if per_fragment_overhead is None:
        usable -= fmt_mod.footer_cost(budget)
    selected: list[SearchResult] = []
    dropped: list[tuple[SearchResult, str]] = []
    used = 0
    chosen_ids: set[str] = set()

    def cost(r: SearchResult) -> int:
        if per_fragment_overhead is not None:
            return _tokens(r) + per_fragment_overhead
        return _tokens(r) + fmt_mod.header_cost(
            r.document_path, r.start_line, r.end_line, r.heading_path or r.symbol
        )

    # 1) Reserva: o melhor fragmento de cada um dos top-N documentos distintos.
    #    Garante que o contexto não colapse numa fonte só.
    reserved: list[SearchResult] = []
    seen_docs: set[str] = set()
    for r in candidates:
        if len(seen_docs) >= min_sources:
            break
        if r.document_path in seen_docs:
            continue
        seen_docs.add(r.document_path)
        reserved.append(r)

    for r in reserved:
        c = cost(r)
        if used + c > usable:
            continue
        selected.append(r)
        chosen_ids.add(r.chunk_id)
        used += c

    # 2) Restante por densidade de valor.
    rest = [r for r in candidates if r.chunk_id not in chosen_ids]
    rest.sort(key=lambda r: -(r.score / max(_tokens(r), 1)))
    for r in rest:
        c = cost(r)
        if used + c <= usable:
            selected.append(r)
            chosen_ids.add(r.chunk_id)
            used += c
        else:
            dropped.append((r, "budget"))

    # Ordem de apresentação volta a ser a de relevância.
    order = {r.chunk_id: i for i, r in enumerate(candidates)}
    selected.sort(key=lambda r: order.get(r.chunk_id, 1_000_000))

    overhead = budget - usable
    return BudgetPlan(tuple(selected), tuple(dropped), used, budget, overhead)


def _tokens(r: SearchResult) -> int:
    n = r.metadata.get("token_count")
    if isinstance(n, int) and n > 0:
        return n
    return count_tokens(r.content)


def fits(fragments: Sequence[str], budget: int) -> bool:
    return sum(count_tokens(f) for f in fragments) <= budget

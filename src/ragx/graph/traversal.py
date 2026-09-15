"""Travessia do grafo, com os limites que impedem a expansão de explodir.

Sem decaimento e sem teto, dois saltos trazem o repositório inteiro.
Ver docs/06-grafo.md.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from ragx.graph.store import GraphStore


@dataclass(frozen=True, slots=True)
class TraversalLimits:
    max_depth: int = 2
    max_nodes: int = 200
    max_fanout: int = 25
    decay: float = 0.6


@dataclass
class Expansion:
    scores: dict[str, float] = field(default_factory=dict)
    depth: dict[str, int] = field(default_factory=dict)
    reason: dict[str, str] = field(default_factory=dict)
    visited: int = 0
    truncated: bool = False


def expand(
    store: GraphStore,
    seeds: dict[str, float],
    limits: TraversalLimits | None = None,
    relation_types: tuple[str, ...] | None = None,
) -> Expansion:
    """BFS com decaimento por salto e penalidade de grau.

    Um `utils.php` importado por tudo não pode dominar o resultado só por ser
    popular — daí a penalidade logarítmica de grau.
    """
    limits = limits or TraversalLimits()
    out = Expansion()
    if not seeds:
        return out

    degrees = store.degrees()
    queue: deque[tuple[str, int, float]] = deque()
    for eid, score in seeds.items():
        out.scores[eid] = score
        out.depth[eid] = 0
        out.reason[eid] = "seed"
        queue.append((eid, 0, score))

    while queue:
        eid, depth, score = queue.popleft()
        out.visited += 1
        if depth >= limits.max_depth:
            continue
        if len(out.scores) >= limits.max_nodes:
            out.truncated = True
            break

        edges = store.neighbors([eid], relation_types)
        edges.sort(key=lambda e: -float(e["weight"]))
        for edge in edges[: limits.max_fanout]:
            other = edge["other_id"]
            if other == eid:
                continue
            degree = max(degrees.get(other, 1), 1)
            penalty = 1.0 / math.log(1.0 + degree + math.e - 1.0)
            new_score = score * (limits.decay ** (depth + 1)) * float(edge["weight"]) * penalty
            if new_score <= out.scores.get(other, 0.0):
                continue
            if other not in out.scores and len(out.scores) >= limits.max_nodes:
                out.truncated = True
                continue
            out.scores[other] = new_score
            out.depth[other] = depth + 1
            out.reason[other] = f"graph:{edge['type']}"
            queue.append((other, depth + 1, new_score))

    return out


def neighborhood(
    store: GraphStore, entity_id: str, depth: int = 1,
    relation_types: tuple[str, ...] | None = None, max_fanout: int = 60,
) -> list[dict[str, object]]:
    """Vizinhança para exibição (`ragx graph <entidade>`), com direção explícita."""
    seen = {entity_id}
    frontier = [entity_id]
    out: list[dict[str, object]] = []
    for level in range(depth):
        edges = store.neighbors(frontier, relation_types)[: max_fanout * (level + 1)]
        nxt: list[str] = []
        for e in edges:
            other = e["other_id"]
            out.append(
                {
                    "direction": e["direction"],
                    "type": e["type"],
                    "other_id": other,
                    "other_name": e["other_name"],
                    "other_type": e["other_type"],
                    "other_qname": e["other_qname"],
                    "confidence": e["confidence"],
                    "depth": level + 1,
                }
            )
            if other not in seen:
                seen.add(other)
                nxt.append(other)
        frontier = nxt
        if not frontier:
            break
    return out

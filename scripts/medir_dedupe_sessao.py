"""Mede o dedupe de sessão em 3 consultas sobrepostas (RAGX-0159).

    uv run python scripts/medir_dedupe_sessao.py [--tokens 3000]

Roda as 3 consultas em sequência por `KnowledgeAPI.build_context`, uma vez com o dedupe de sessão e uma
sem, e imprime os tokens entregues por chamada, quantos `chunk_id` se repetem entre as chamadas e os
tokens economizados. Usa o índice do projeto atual (somente leitura).
"""

from __future__ import annotations

import argparse
import re

from ragx.config import load_config
from ragx.mcp.server import KnowledgeAPI
from ragx.mcp.tools import BuildContextRequest

CONSULTAS = [
    "como o embedder é cacheado",
    "build_embedder cache por processo",
    "cache do embedder e dimensão",
]


def rodar(cfg, tokens: int, dedupe: bool) -> list[dict]:  # type: ignore[no-untyped-def]
    cfg = cfg.model_copy(deep=True)
    cfg.context.session_dedupe = dedupe
    api = KnowledgeAPI(cfg)
    saidas = []
    for q in CONSULTAS:
        d = api.build_context(BuildContextRequest(query=q, tokens=tokens, format="json"))["data"]
        saidas.append(d)
    return saidas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=3000)
    a = ap.parse_args()
    cfg = load_config()
    sem = rodar(cfg, a.tokens, dedupe=False)
    com = rodar(cfg, a.tokens, dedupe=True)

    vistos: set[str] = set()
    repetidos = []
    for d in sem:
        ids = {f["chunk_id"] for f in d["fragments"]}
        repetidos.append(len(ids & vistos))
        vistos |= ids
    print(f"{'consulta':40s} {'sem dedupe':>11s} {'com dedupe':>11s} {'refs':>5s} {'repetidos':>9s}")
    for q, s, c, r in zip(CONSULTAS, sem, com, repetidos, strict=True):
        print(f"{q[:40]:40s} {s['estimated_tokens']:11d} {c['estimated_tokens']:11d} {c.get('dedupe_refs', 0):5d} {r:9d}")
    total_sem = sum(d["estimated_tokens"] for d in sem)
    total_com = sum(d["estimated_tokens"] for d in com)
    print(f"\ntotal: {total_sem} -> {total_com} tokens  ({100 * (total_com - total_sem) / total_sem:+.1f}%)")
    print("economizados (dedupe_saved_tokens):", sum(d.get("dedupe_saved_tokens", 0) for d in com))
    md = com[-1].get("markdown", "")
    print("linha de referências presente na última:", bool(re.search(r"Já entregues nesta sessão", md)) or bool(com[-1].get("references")))


if __name__ == "__main__":
    main()

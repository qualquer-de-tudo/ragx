"""Mede a expansão do grafo sobre o conjunto de consultas do repositório (RAGX-0145).

    uv run python scripts/medir_grafo.py [--consultas tests/eval/queries.yaml] [--n 12] \
        [--path "src/ragx/*"] [--lang python]

Para cada consulta roda `graph_search` (a mesma chamada de `build_context`, pedindo `limit=25`) e
imprime: sementes, nós visitados e expandidos, se truncou, quantos chunks vieram SÓ do grafo, o tempo
do grafo sem a busca base e, com `--path`/`--lang`, quantos resultados ficaram fora do filtro. No fim,
recall@5 e MRR do resultado do grafo contra `relevant_paths`, e a ordem dos IDs numa 2ª execução
(determinismo).
"""

from __future__ import annotations

import argparse
import fnmatch
import statistics
from pathlib import Path

from ragx.config import load_config
from ragx.graph.service import graph_search
from ragx.search.evaluation import load_cases
from ragx.search.service import SearchFilters, search


def _fora(path: str, glob: str | None) -> bool:
    return bool(glob) and not fnmatch.fnmatch(path, glob)  # type: ignore[arg-type]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consultas", type=Path, default=Path("tests/eval/queries.yaml"))
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--path", default=None, help="path_glob (usa * como curinga)")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--seed-top-k", type=int, default=None, help="sobrescreve [graph] seed_top_k")
    ap.add_argument("--resumo", action="store_true", help="só o resumo")
    a = ap.parse_args()

    cfg = load_config()
    if a.seed_top_k is not None:
        cfg.graph.seed_top_k = a.seed_top_k
    casos = load_cases(a.consultas if a.consultas.is_absolute() else cfg.root / a.consultas, only_answerable=True)[: a.n]
    filtros = SearchFilters(lang=a.lang, path_glob=a.path)

    linhas = []
    hits5 = 0
    rr = 0.0
    fora_total = total = 0
    deterministico = True
    for caso in casos:
        out = graph_search(cfg, caso.query, limit=25, depth=1, filters=filtros)
        again = graph_search(cfg, caso.query, limit=25, depth=1, filters=filtros)
        deterministico &= [r.chunk_id for r in out.results] == [r.chunk_id for r in again.results]
        # chunks do resultado que a busca base NÃO trouxe (só o grafo): o campo existe depois da
        # RAGX-0145; antes, a mesma conta sai da diferença contra a busca base
        so_grafo = getattr(out, "graph_only", None)
        if so_grafo is None:
            base_ids = {r.chunk_id for r in search(cfg, caso.query, mode="hybrid", limit=50, filters=filtros).results}
            so_grafo = sum(1 for r in out.results if r.chunk_id not in base_ids)
        fora = sum(1 for r in out.results if _fora(r.document_path, a.path.replace("%", "*") if a.path else None))
        fora_total += fora
        total += len(out.results)
        caminhos = [r.document_path for r in out.results]
        pos = next((i for i, p in enumerate(caminhos, 1) if p in caso.relevant_paths), None)
        hits5 += 1 if pos is not None and pos <= 5 else 0
        rr += 1 / pos if pos else 0.0
        linhas.append((
            out.seeds, out.expansion.visited, len(out.expansion.scores),
            out.expansion.truncated, so_grafo, out.timings_ms.get("graph", 0.0), fora,
        ))
        if not a.resumo:
            print(
                f"sementes={out.seeds:4d} visitados={out.expansion.visited:4d} nos={len(out.expansion.scores):4d} "
                f"truncou={int(out.expansion.truncated)} so_grafo={so_grafo:2d} "
                f"grafo_ms={out.timings_ms.get('graph', 0):6.1f} fora_do_filtro={fora:2d}  {caso.query[:50]}"
            )
    n = len(linhas)
    print("\n== resumo")
    print(f"consultas: {n}")
    print(f"sementes: min {min(x[0] for x in linhas)}  max {max(x[0] for x in linhas)}  mediana {statistics.median(x[0] for x in linhas):.0f}")
    print(f"visitados: max {max(x[1] for x in linhas)}   consultas com truncated: {sum(1 for x in linhas if x[3])} de {n}")
    print(f"consultas com chunk SÓ do grafo: {sum(1 for x in linhas if x[4])} de {n}   (total de chunks só do grafo: {sum(x[4] for x in linhas)})")
    print(f"custo do grafo (sem a busca base): mediana {statistics.median(x[5] for x in linhas):.1f} ms   max {max(x[5] for x in linhas):.1f} ms")
    if a.path:
        print(f"resultados fora do filtro: {fora_total} de {total}")
    print(f"recall@5 do grafo: {hits5 / n:.3f}   MRR: {rr / n:.3f}   determinismo: {'ok' if deterministico else 'FALHOU'}")


if __name__ == "__main__":
    main()

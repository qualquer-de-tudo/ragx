"""Mede o `ragx sync` num clone novo (RAGX-0144): textos enviados ao embedder, tempo e recall.

    uv run python scripts/medir_clone_novo.py [PASTA-DO-REPO] [--sem-import] [--sem-modelo-copiado]

Clona `PASTA-DO-REPO` (padrão: o diretório atual) com `git clone` numa pasta temporária, copia a pasta de
modelos do fastembed do repositório de origem (para não baixar 240 MB de novo: não faz parte da medição),
roda `sync` e imprime:

- textos enviados ao embedder durante o `sync` (antes da correção: todos os chunks);
- tempo do `sync` e vetores importados / ainda só grosseiros;
- recall@5, MRR e nDCG@10 do modo híbrido nas consultas de `tests/eval/queries.yaml`, com o int8 importado
  e depois de completar o float32 (`embed_pending(upgrade_coarse=True)`).

`--sem-import` apaga `knowledge/embeddings` do clone antes do `sync`, reproduzindo o comportamento de antes
(reembutir tudo).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("origem", nargs="?", default=".")
    ap.add_argument("--sem-import", action="store_true")
    ap.add_argument("--sem-modelo-copiado", action="store_true")
    a = ap.parse_args()

    origem = Path(a.origem).resolve()
    clone = Path(tempfile.mkdtemp(prefix="clone_")) / "repo"
    subprocess.run(["git", "clone", "-q", str(origem), str(clone)], check=True)
    if not a.sem_modelo_copiado and (origem / ".ragx" / "cache" / "models").is_dir():
        shutil.copytree(origem / ".ragx" / "cache" / "models", clone / ".ragx" / "cache" / "models")
    if a.sem_import:
        shutil.rmtree(clone / "knowledge" / "embeddings", ignore_errors=True)

    from ragx.config import load_config
    from ragx.embeddings.fastembed_provider import FastEmbedEmbedder
    from ragx.indexing.embed import embed_pending
    from ragx.search.evaluation import evaluate, load_cases
    from ragx.storage.db import open_db
    from ragx.sync.service import sync

    enviados = {"n": 0}
    original = FastEmbedEmbedder.embed_documents

    def espia(self, textos):  # type: ignore[no-untyped-def]
        enviados["n"] += len(textos)
        return original(self, textos)

    FastEmbedEmbedder.embed_documents = espia  # type: ignore[method-assign]

    cfg = load_config(clone)
    t0 = time.perf_counter()
    rel = sync(cfg, write_knowledge=False)
    dur = time.perf_counter() - t0
    with open_db(cfg.db_path, read_only=True) as c:
        chunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"chunks no clone: {chunks}")
    print(f"textos enviados ao embedder no sync: {enviados['n']}")
    print(f"sync: {dur:.1f} s   importados: {rel.imported_embeddings}   só grosseiros: {rel.coarse_only}   embutidos: {rel.embedded}")
    if rel.warnings:
        print("avisos:", [w[:90] for w in rel.warnings])

    cases = load_cases(clone / "tests" / "eval" / "queries.yaml")

    def metricas(rotulo: str) -> None:
        m = evaluate(cfg, cases, ("hybrid",))[0]
        print(f"{rotulo}: recall@5 {m.recall_at_5:.3f}  MRR {m.mrr:.3f}  nDCG@10 {m.ndcg_at_10:.3f}  (n={m.cases})")

    metricas("híbrido com o int8 importado" if not a.sem_import else "híbrido (reembutido do zero)")
    if rel.coarse_only:
        t1 = time.perf_counter()
        with open_db(cfg.db_path) as conn:
            embed_pending(cfg, conn, upgrade_coarse=True)
            conn.commit()
        print(f"completar o float32 (embed-only): {time.perf_counter() - t1:.1f} s")
        metricas("híbrido com float32 completo")


if __name__ == "__main__":
    main()

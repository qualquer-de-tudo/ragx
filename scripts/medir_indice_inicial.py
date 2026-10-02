"""Mede o primeiro índice de um projeto sintético, por fase do `embed_pending` (RAGX-0146).

    uv run python scripts/medir_indice_inicial.py --arquivos 400 --provider hashing

Gera `--arquivos` arquivos Python (várias funções cada, ~9 chunks por arquivo), roda `ragx index` com o provider
`hashing` (isola o cache do modelo) e imprime o tempo total e o de cada fase do embedding: leitura do cache (`get`
ou `get_many`), montagem do prefixo (`_prefixed`), `embed_documents`, escrita do cache (`put` ou `put_many`) e
`store_vectors`. Funciona nas duas formas do cache (por arquivo e SQLite em lote), medindo o que existir.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path

FASES: dict[str, float] = defaultdict(float)
CHAMADAS: dict[str, int] = defaultdict(int)


def _medir(obj: object, nome: str, rotulo: str) -> None:
    original = getattr(obj, nome, None)
    if original is None:
        return

    def embrulho(*a: object, **k: object) -> object:
        t0 = time.perf_counter()
        try:
            return original(*a, **k)
        finally:
            FASES[rotulo] += time.perf_counter() - t0
            CHAMADAS[rotulo] += 1

    setattr(obj, nome, embrulho)


def _gerar(raiz: Path, n: int) -> None:
    for i in range(n):
        corpo = [f'"""Módulo {i} do projeto sintético."""\n']
        for j in range(9):
            corpo.append(
                f"\n\ndef funcao_{i}_{j}(valor, fator):\n"
                f'    """Calcula o item {j} do módulo {i} com um fator."""\n'
                f"    total = 0\n    for k in range(valor):\n        total += k * fator + {i + j}\n"
                f"    return total + {i * j}\n"
            )
        pasta = raiz / f"pkg{i % 20}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"mod_{i}.py").write_text("".join(corpo), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivos", type=int, default=400)
    ap.add_argument("--provider", default="hashing")
    ap.add_argument("--segunda-rodada", action="store_true", help="roda de novo para medir o índice sem mudança")
    args = ap.parse_args()
    origem = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp) / "projeto"
        raiz.mkdir()
        home = Path(tmp) / "home"
        home.mkdir()
        os.environ["RAGX_HOME"] = str(home)
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)
        _gerar(raiz, args.arquivos)
        (raiz / "ragx.toml").write_text(
            '[project]\nname = "sintetico"\nid = "sintetico"\n\n'
            f'[embedding]\nprovider = "{args.provider}"\ndim = 64\nversioned_dim = 32\n',
            encoding="utf-8",
        )
        os.chdir(raiz)

        from ragx.config import load_config
        from ragx.embeddings import base as emb_base
        from ragx.indexing import embed as embed_mod
        from ragx.indexing.pipeline import index_project
        from ragx.storage import vectors as vec_mod

        for nome in ("get", "put", "get_many", "put_many"):
            _medir(emb_base.EmbeddingCache, nome, f"cache.{nome}")
        _medir(embed_mod, "_prefixed", "_prefixed")
        _medir(embed_mod, "store_vectors", "store_vectors")
        _medir(vec_mod, "pending_for_embedding", "pending_for_embedding")
        _medir(vec_mod, "missing_chunk_ids", "missing_chunk_ids")

        cfg = load_config(raiz)
        t0 = time.perf_counter()
        report = index_project(cfg, embed=True)
        total = time.perf_counter() - t0

        chunks = getattr(report, "chunks", None)
        print(f"arquivos: {args.arquivos}  chunks: {chunks}  provider: {args.provider}")
        print(f"primeiro índice, total: {total:.2f} s")
        for rotulo in sorted(FASES):
            print(f"  {rotulo:24s} {FASES[rotulo]:7.3f} s  ({CHAMADAS[rotulo]} chamadas)")
        cache_dir = cfg.state_dir / "cache" / "emb"
        arquivos = [p for p in cache_dir.rglob("*") if p.is_file()] if cache_dir.exists() else []
        print(f"arquivos criados em .ragx/cache/emb: {len(arquivos)}")

        if args.segunda_rodada:
            FASES.clear()
            CHAMADAS.clear()
            t0 = time.perf_counter()
            index_project(cfg, embed=True)
            print(f"segunda rodada (sem mudança): {time.perf_counter() - t0:.2f} s")
        os.chdir(origem)  # o Windows não apaga a pasta em que o processo está


if __name__ == "__main__":
    main()

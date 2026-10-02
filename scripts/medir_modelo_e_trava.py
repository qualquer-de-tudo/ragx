"""Mede as duas arestas da RAGX-0153, sem tocar em nenhum projeto real.

    uv run python scripts/medir_modelo_e_trava.py [--download]

1. Tamanho de `.ragx/cache/models` em `--projeto` (padrão: o diretório atual).
2. Com `--download`: quanto leva o PRIMEIRO uso do fastembed numa pasta de modelos vazia (download + carga) e o
   segundo (só a carga), em pasta temporária.
3. A trava "imortal": um `index.lock` com o PID de um processo VIVO qualquer (o deste mesmo script, com o `proc`
   de OUTRO processo gravado, quando o campo existir) bloqueia `try_acquire`?
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path


def tamanho_mb(pasta: Path) -> float:
    if not pasta.exists():
        return 0.0
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) / 2**20


def modelos(projeto: Path) -> None:
    print(f"cache de modelos em {projeto / '.ragx/cache/models'}: {tamanho_mb(projeto / '.ragx/cache/models'):.0f} MB")


def download() -> None:
    from ragx.embeddings.fastembed_provider import DEFAULT_MODEL, FastEmbedEmbedder

    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp) / "models"
        t0 = time.perf_counter()
        emb = FastEmbedEmbedder(model=DEFAULT_MODEL, dim=384, cache_dir=pasta)
        emb.embed_documents(["primeiro uso"])
        t1 = time.perf_counter()
        print(f"1º uso (download + carga), pasta vazia: {t1 - t0:.1f} s; pasta com {tamanho_mb(pasta):.0f} MB")
        t2 = time.perf_counter()
        emb2 = FastEmbedEmbedder(model=DEFAULT_MODEL, dim=384, cache_dir=pasta)
        emb2.embed_documents(["segundo uso"])
        print(f"2º uso (só a carga), mesma pasta: {time.perf_counter() - t2:.1f} s")


def trava_imortal() -> None:
    from ragx.indexing import lock

    with tempfile.TemporaryDirectory() as tmp:
        estado = Path(tmp)
        # um indexador "morto" cujo PID foi reaproveitado: o PID é o DESTE processo (vivo), o `proc` é de outra era
        payload = {"pid": os.getpid(), "op": "index", "source": "cli", "started_at": "2020-01-01T00:00:00Z"}
        if hasattr(lock, "proc_token"):
            payload["proc"] = "token-de-outro-processo-que-ja-morreu"
        (estado / lock.LOCK_NAME).write_text(json.dumps(payload), encoding="utf-8")
        conseguiu = lock.try_acquire(estado, "index", "cli")
        print(f"trava de PID reutilizado (PID vivo, dono morto): try_acquire = {conseguiu} (True = assumiu; False = bloqueia para sempre)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", default=".")
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()
    modelos(Path(args.projeto))
    if args.download:
        download()
    trava_imortal()


if __name__ == "__main__":
    main()

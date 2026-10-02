"""Mede a varredura de uma árvore SEM mudança (RAGX-0196, S4): o custo por arquivo de `iter_candidates`.

    uv run python scripts/medir_varredura.py [--arquivos 20000]

Gera `--arquivos` arquivos pequenos em pastas temporárias, monta o mapa `size+mtime` como o `index` sem mudança o teria e
cronometra `iter_candidates` (a decisão barata de cada arquivo: ignore, veredito, `unchanged`). Não indexa nada e não
toca em nenhum projeto real; imprime a mediana de 5 rodadas.
"""

from __future__ import annotations

import argparse
import os
import statistics
import tempfile
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivos", type=int, default=20000)
    args = ap.parse_args()
    from ragx.security.gate import SecurityGate
    from ragx.walk import iter_candidates

    origem = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp) / "p"
        raiz.mkdir()
        for i in range(args.arquivos):
            pasta = raiz / f"pkg{i % 40}" / f"sub{i % 7}"
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / f"m{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
        (raiz / ".gitignore").write_text("build/\n*.log\n__pycache__/\n", encoding="utf-8")
        os.chdir(raiz)
        gate = SecurityGate(raiz)
        fp: dict[str, tuple[int, int]] = {}
        for caminho in raiz.rglob("*.py"):
            st = caminho.stat()
            fp[caminho.relative_to(raiz).as_posix()] = (st.st_size, st.st_mtime_ns)
        tempos = []
        for _ in range(5):
            t0 = time.perf_counter()
            n = sum(1 for _ in iter_candidates(raiz, gate, fingerprints=fp))
            tempos.append(time.perf_counter() - t0)
        mediana = statistics.median(tempos)
        print(f"{n} arquivos decididos; mediana {mediana:.2f} s (min {min(tempos):.2f}, max {max(tempos):.2f}); {1e6 * mediana / n:.0f} us por arquivo")
        os.chdir(origem)


if __name__ == "__main__":
    main()

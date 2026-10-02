"""Mede o ciclo ocioso do `ragx watch` (RAGX-0147).

    uv run python scripts/medir_watch.py --arquivos 643 --ciclos 50 [--perfil]

Gera um projeto sintético (pastas com arquivos `.py`, mais um `.gitignore` e uma árvore ignorada), indexa uma vez e
roda `watch(max_cycles=N)` sem dormir, cronometrando cada ciclo ocioso de fora (o laço não muda). Imprime mediana e
p95 em ms, quantas vezes o `SecurityGate` foi construído e, com `--perfil`, o `cProfile` de um ciclo.
"""

from __future__ import annotations

import argparse
import cProfile
import os
import pstats
import statistics
import tempfile
import time
from pathlib import Path

CONSTRUCOES = {"gate": 0}


def _gerar(raiz: Path, n: int) -> None:
    (raiz / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")
    for i in range(n):
        pasta = raiz / f"pkg{i % 25}" / f"sub{i % 7}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    (raiz / "build").mkdir()
    for i in range(30):
        (raiz / "build" / f"gerado{i}.py").write_text("x = 1\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivos", type=int, default=643)
    ap.add_argument("--ciclos", type=int, default=50)
    ap.add_argument("--perfil", action="store_true")
    args = ap.parse_args()
    origem = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp) / "p"
        raiz.mkdir()
        home = Path(tmp) / "home"
        home.mkdir()
        for var in ("HOME", "USERPROFILE", "RAGX_HOME"):
            os.environ[var] = str(home)
        _gerar(raiz, args.arquivos)
        (raiz / "ragx.toml").write_text(
            '[project]\nname = "w"\nid = "w"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
            encoding="utf-8",
        )
        os.chdir(raiz)

        from ragx.config import load_config
        from ragx.indexing.pipeline import index_project
        from ragx.security import gate as gate_mod
        from ragx.watch import monitor

        cfg = load_config(raiz)
        index_project(cfg, embed=False)

        original_init = gate_mod.SecurityGate.__init__

        def conta(self, *a, **k):  # type: ignore[no-untyped-def]
            CONSTRUCOES["gate"] += 1
            original_init(self, *a, **k)

        gate_mod.SecurityGate.__init__ = conta  # type: ignore[method-assign]

        tempos: list[float] = []
        marca = [time.perf_counter()]

        def sleep(_s: float) -> None:
            marca[0] = time.perf_counter()

        def on_event(kind: str, _d: object, _s: object) -> None:
            tempos.append((time.perf_counter() - marca[0]) * 1000)

        t0 = time.perf_counter()
        monitor.watch(cfg, on_event=on_event, max_cycles=args.ciclos, sleep=sleep)
        total = time.perf_counter() - t0
        tempos.sort()
        p50 = statistics.median(tempos)
        p95 = tempos[int(len(tempos) * 0.95) - 1]
        print(f"arquivos: {args.arquivos}  ciclos ociosos: {len(tempos)}")
        print(f"ciclo ocioso: mediana {p50:.1f} ms, p95 {p95:.1f} ms  (total {total:.2f} s)")
        print(f"SecurityGate construído: {CONSTRUCOES['gate']} vez(es) em {args.ciclos} ciclos (+1 do início)")

        if args.perfil:
            pr = cProfile.Profile()
            pr.enable()
            monitor.watch(cfg, max_cycles=1, sleep=lambda _s: None)
            pr.disable()
            pstats.Stats(pr).sort_stats("cumulative").print_stats(14)
        os.chdir(origem)


if __name__ == "__main__":
    main()

"""Mede a rodada de `index_project` SEM mudança num repositório git sintético (RAGX-0198, S4).

    uv run python scripts/medir_sem_mudanca.py [--arquivos 20000] [--rodadas 5]

Gera `--arquivos` arquivos pequenos em pastas temporárias, com pastas ignoradas de verdade (`node_modules/` e `build/`
no `.gitignore`, um `.gitignore` aninhado, arquivos `*.log`), faz `git init` e um commit, indexa uma vez (provider
`hashing`, sem rede) e cronometra as rodadas seguintes sem mudança, como o hook de commit as dispara. Quando o
`index_project` aceita `full_scan`, mede também a varredura completa forçada, para comparar os dois caminhos na mesma
árvore. Não toca em nenhum projeto real; imprime mediana, mínimo e máximo.
"""

from __future__ import annotations

import argparse
import inspect
import os
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


def _git(raiz: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=medicao", "-c", "user.email=medicao@exemplo.invalid",
         "-c", "core.autocrlf=false", *args],
        cwd=raiz, check=True, capture_output=True,
    )


def _gerar(raiz: Path, n: int) -> None:
    for i in range(n):
        pasta = raiz / f"pkg{i % 40}" / f"sub{i % 7}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"m{i}.py").write_text(f"def f_{i}():\n    return {i}\n", encoding="utf-8")
    # pastas ignoradas pelo git e pelo RAGX: a varredura poda, o git nem lista
    for i in range(2000):
        pasta = raiz / "node_modules" / f"lib{i % 50}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"i{i}.js").write_text(f"module.exports = {i};\n", encoding="utf-8")
    (raiz / "build").mkdir()
    for i in range(200):
        (raiz / "build" / f"out{i}.txt").write_text("saida\n", encoding="utf-8")
    for i in range(50):
        (raiz / f"pkg{i % 40}" / f"execucao{i}.log").write_text("log\n", encoding="utf-8")
    (raiz / ".gitignore").write_text("node_modules/\nbuild/\n*.log\n.ragx/\n", encoding="utf-8")
    (raiz / "pkg3" / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (raiz / "pkg3" / "rascunho.tmp").write_text("temporario\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivos", type=int, default=20000)
    ap.add_argument("--rodadas", type=int, default=5)
    args = ap.parse_args()
    origem = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp) / "projeto"
        raiz.mkdir()
        home = Path(tmp) / "home"
        home.mkdir()
        os.environ["RAGX_HOME"] = str(home)
        _gerar(raiz, args.arquivos)
        (raiz / "ragx.toml").write_text(
            '[project]\nname = "sintetico"\nid = "sintetico"\n\n'
            '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
            encoding="utf-8",
        )
        _git(raiz, "init", "-q")
        _git(raiz, "add", "-A")
        _git(raiz, "commit", "-q", "-m", "inicial")
        os.chdir(raiz)

        from ragx.config import load_config
        from ragx.indexing.pipeline import index_project

        cfg = load_config(raiz)
        t0 = time.perf_counter()
        primeiro = index_project(cfg, embed=True)
        print(f"{args.arquivos} arquivos; primeiro índice {time.perf_counter() - t0:.1f} s, "
              f"{primeiro.stats.indexed} documentos")

        caminhos: list[tuple[str, dict[str, bool]]] = [("padrão", {})]
        if "full_scan" in inspect.signature(index_project).parameters:
            caminhos.append(("varredura completa (--full-scan)", {"full_scan": True}))
        for rotulo, kw in caminhos:
            tempos = []
            for _ in range(args.rodadas):
                t0 = time.perf_counter()
                r = index_project(cfg, source="hook:post-commit", **kw)
                tempos.append(time.perf_counter() - t0)
            via = getattr(r, "scan_mode", "?")
            print(f"{rotulo:34s} mediana {statistics.median(tempos):.2f} s "
                  f"(min {min(tempos):.2f}, max {max(tempos):.2f}); arquivos vistos {r.stats.files_seen}, "
                  f"indexados {r.stats.indexed}, modo {via}")
        os.chdir(origem)  # o Windows não apaga a pasta em que o processo está


if __name__ == "__main__":
    main()

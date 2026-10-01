"""Mede o custo dos hooks que rodam em TODA sessão e TODO commit (RAGX-0143, S7 e S8).

    uv run python scripts/medir_hooks.py --n 12 [--entrada ragx.entry]

Cria um projeto sintético indexado (com `git init`), roda cada comando N vezes por
`python -m <entrada>` e imprime mediana, mínimo e máximo em ms:

- `claude hint`: o `SessionStart` do Claude Code (S7, meta de 120 ms);
- `hook-run post-commit`: a parte síncrona do hook de commit (S8, meta de 150 ms);
- `hook-run post-checkout A B 0` (arquivo): devia ser um no-op.

`--entrada ragx.cli.main` mede o caminho antigo (a CLI completa); `ragx.entry`, o novo. Sem
`--entrada`, mede os dois.
"""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOML = '[project]\nname = "medicao"\nid = "medicao"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


def _projeto() -> Path:
    raiz = Path(tempfile.mkdtemp(prefix="hooks_"))
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    (raiz / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
    subprocess.run(
        [sys.executable, "-m", "ragx.cli.main", "index", str(raiz), "--quiet"],
        cwd=raiz, check=True, capture_output=True,
    )
    return raiz


def _medir(entrada: str, args: list[str], raiz: Path, n: int, claude: bool) -> list[float]:
    env = dict(os.environ)
    if claude:
        env["CLAUDECODE"] = "1"
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, "-m", entrada, *args], cwd=raiz, env=env,
            stdin=subprocess.DEVNULL, capture_output=True, check=False,
        )
        out.append((time.perf_counter() - t0) * 1000)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--entrada", action="append", help="módulo de entrada (repetível)")
    a = ap.parse_args()
    entradas = a.entrada or ["ragx.cli.main", "ragx.entry"]
    raiz = _projeto()
    casos = [
        ("claude hint", ["claude", "hint"], False),
        ("hook-run post-commit", ["hook-run", "post-commit", "--root", str(raiz)], False),
        ("hook-run post-checkout (arquivo)", ["hook-run", "post-checkout", "A", "B", "0", "--root", str(raiz)], False),
    ]
    for entrada in entradas:
        print(f"\n== {entrada}")
        for nome, args, claude in casos:
            try:
                tempos = _medir(entrada, args, raiz, a.n, claude)
            except OSError as exc:
                print(f"  {nome}: falhou ({exc})")
                continue
            print(
                f"  {nome:<34} p50 {statistics.median(tempos):6.0f} ms   "
                f"min {min(tempos):6.0f}   max {max(tempos):6.0f}"
            )
    time.sleep(3)  # deixa as indexações destacadas terminarem antes de apagar nada


if __name__ == "__main__":
    main()

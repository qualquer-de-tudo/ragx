"""Mede a estabilidade de `knowledge/` (RAGX-0148), num projeto sintético temporário.

    uv run python scripts/medir_knowledge_estavel.py [--arquivos 40]

1. `ragx sync` duas vezes sem mudança: quantos arquivos de `knowledge/` mudam (hash) e quantos têm o mtime trocado;
2. edita UMA função, `sync`: quantos arquivos mudam, por pasta (`chunks/`, `documents/`, `entities/`, `relations/`...).
Nunca toca o `knowledge/` do repositório do RAGX: tudo roda em `tempfile`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from collections import Counter
from pathlib import Path


def _gerar(raiz: Path, n: int) -> None:
    for i in range(n):
        pasta = raiz / f"pkg{i % 5}"
        pasta.mkdir(parents=True, exist_ok=True)
        outro = (i + 1) % n
        (pasta / f"m{i}.py").write_text(
            f"from pkg{outro % 5}.m{outro} import f{outro}_0\n\n\n"
            + "".join(
                f"def f{i}_{j}(x):\n    '''Item {j} do módulo {i}.'''\n    return f{outro}_0(x) + {i + j}\n\n\n"
                for j in range(4)
            ),
            encoding="utf-8",
        )


def _estado(alvo: Path) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for p in alvo.rglob("*"):
        if p.is_file():
            out[p.relative_to(alvo).as_posix()] = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
    return out


def _comparar(antes: dict, depois: dict) -> tuple[list[str], list[str]]:
    mudou = sorted(k for k in depois if k not in antes or antes[k][0] != depois[k][0]) + sorted(
        k for k in antes if k not in depois
    )
    so_mtime = sorted(k for k in depois if k in antes and antes[k][0] == depois[k][0] and antes[k][1] != depois[k][1])
    return mudou, so_mtime


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivos", type=int, default=40)
    ap.add_argument("--copiar", help="pasta real a copiar (ex.: src/ragx) em vez do projeto sintético; edita o 1º .py com mais de 40 linhas")
    args = ap.parse_args()
    origem = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp) / "p"
        raiz.mkdir()
        home = Path(tmp) / "home"
        home.mkdir()
        for var in ("HOME", "USERPROFILE", "RAGX_HOME"):
            os.environ[var] = str(home)
        if args.copiar:
            import shutil

            shutil.copytree(origem / args.copiar, raiz / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            _gerar(raiz, args.arquivos)
        (raiz / "ragx.toml").write_text(
            '[project]\nname = "k"\nid = "k"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
            encoding="utf-8",
        )
        os.chdir(raiz)
        from ragx.config import load_config
        from ragx.indexing.pipeline import index_project
        from ragx.sync.service import sync

        cfg = load_config(raiz)
        index_project(cfg)
        r0 = sync(cfg, full=True)
        alvo = raiz / "knowledge"
        base = _estado(alvo)
        print(f"projeto: {args.arquivos} arquivos, {len(base)} arquivos em knowledge/ depois do 1º sync")

        r1 = sync(cfg, full=True)
        e1 = _estado(alvo)
        mudou, so_mtime = _comparar(base, e1)
        print(f"2º sync sem mudança: conteúdo mudou em {len(mudou)}: {mudou[:5]}; só mtime em {len(so_mtime)}")
        print(f"  files_changed reportado: {getattr(r1.serialized, 'files_changed', 'n/a')}")

        if args.copiar:
            alvo_py = next(
                p for p in sorted((raiz / "src").rglob("*.py")) if len(p.read_text(encoding="utf-8").splitlines()) > 40
            )
            alvo_py.write_text(
                alvo_py.read_text(encoding="utf-8") + "\n\ndef funcao_editada_0148():\n    return 1\n", encoding="utf-8"
            )
        else:
            alvo_py = raiz / "pkg2" / "m2.py"
            alvo_py.write_text(alvo_py.read_text(encoding="utf-8").replace("+ 2\n", "+ 9999\n", 1), encoding="utf-8")
        index_project(cfg)
        r2 = sync(cfg, full=True)
        e2 = _estado(alvo)
        mudou2, _ = _comparar(e1, e2)
        por_pasta = Counter(k.split("/")[0] for k in mudou2)
        print(f"editar 1 função: {len(mudou2)} arquivos de knowledge/ mudaram: {dict(por_pasta)}")
        print(f"  files_changed reportado: {getattr(r2.serialized, 'files_changed', 'n/a')}")
        del r0
        os.chdir(origem)


if __name__ == "__main__":
    main()

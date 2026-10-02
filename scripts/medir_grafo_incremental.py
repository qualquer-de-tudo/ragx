"""Mede o grafo incremental por documento (RAGX-0151), sem tocar no `knowledge/` do repositório.

    uv run python scripts/medir_grafo_incremental.py [--commits 100] [--modulos 400]

1. Fração de edições que NÃO mudam o conjunto de símbolos: nos últimos `--commits` commits do repositório, para
   cada arquivo Python alterado (modo `M`), compara os nomes `class`/`function`/`method` antes e depois com o
   mesmo parser e chunker do índice. Se a fração for pequena, o caminho rápido quase nunca vale.
2. Tempos, num projeto sintético temporário com `--modulos` módulos: rebuild completo, `update_documents` de um
   corpo editado e de um símbolo novo (que cai no completo), e quantas entidades ficam sem `chunk_id` depois de
   editar uma linha só com o índice (antes) e depois do `update_documents`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import time
from pathlib import Path

from ragx.indexing.chunkers import ChunkOptions, chunk_document
from ragx.indexing.parsers import parse

_TIPOS = {"class", "function", "method"}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    ).stdout


def _simbolos(rel: str, texto: str) -> frozenset[str] | None:
    parsed = parse(rel, texto)
    if parsed is None:
        return None
    return frozenset(
        f"{c.kind.value}:{c.symbol}" for c in chunk_document(rel, texto, parsed, ChunkOptions()) if c.symbol and c.kind.value in _TIPOS
    )


def fracao_sem_mudanca_de_simbolos(commits: int) -> None:
    lista = _git("log", f"-{commits}", "--format=%H").split()
    iguais = diferentes = 0
    for sha in lista:
        for linha in _git("diff", "--name-status", "--diff-filter=M", f"{sha}^", sha).splitlines():
            _status, _, rel = linha.partition("\t")
            if not rel.endswith(".py"):
                continue
            antes = _git("show", f"{sha}^:{rel}")
            depois = _git("show", f"{sha}:{rel}")
            a, b = _simbolos(rel, antes), _simbolos(rel, depois)
            if a is None or b is None:
                continue
            if a == b:
                iguais += 1
            else:
                diferentes += 1
    total = iguais + diferentes
    pct = 100 * iguais / total if total else 0.0
    print(f"edições de arquivo .py em {len(lista)} commits: {total}; mesmo conjunto de símbolos: {iguais} ({pct:.1f}%); mudou: {diferentes}")


def _modulo(i: int, j: int) -> str:
    return f'''from mod{j} import Cls{j}


class Cls{i}:
    """Servico {i}."""

    def run_{i}(self, x):
        """Executa o servico {i} e delega ao vizinho."""
        total = Cls{j}().run_{j}(x) + {i}
        for item in range({i} + 3):
            total += item * {i}
        return total

    def verificar_{i}(self, valor):
        """Valida o valor recebido pelo servico {i}."""
        if valor is None:
            raise ValueError("valor ausente")
        return Cls{j}().run_{j}(valor) > {i}


def func_{i}(x):
    """Funcao de entrada do modulo {i}."""
    resultado = Cls{i}().run_{i}(x)
    resultado += Cls{j}().run_{j}(x) * {i}
    return resultado
'''


def tempos(n: int) -> None:
    origem = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp) / "p"
        raiz.mkdir()
        casa = Path(tmp) / "home"
        casa.mkdir()
        for var in ("HOME", "USERPROFILE", "RAGX_HOME"):
            os.environ[var] = str(casa)
        (raiz / "ragx.toml").write_text(
            '[project]\nname = "g"\nid = "g"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
            encoding="utf-8",
        )
        for i in range(n):
            (raiz / f"mod{i}.py").write_text(_modulo(i, (i + 1) % n), encoding="utf-8")
        os.chdir(raiz)
        from ragx.config import load_config
        from ragx.graph.service import rebuild, update_documents
        from ragx.indexing.pipeline import index_project
        from ragx.storage.db import open_db

        cfg = load_config(raiz)
        index_project(cfg)
        completo = [rebuild(cfg) for _ in range(3)]
        ms_completo = sorted(r.duration_ms for r in completo)[1]
        print(f"{n} módulos: {completo[-1].stats.entities} entidades, {completo[-1].stats.relations} relações")
        print(f"rebuild completo (mediana de 3): {ms_completo} ms")

        def sem_chunk() -> int:
            with open_db(cfg.db_path, read_only=True) as conn:
                return int(conn.execute("SELECT COUNT(*) FROM entities WHERE chunk_id IS NULL AND type NOT IN ('file','technology')").fetchone()[0])

        arq = raiz / f"mod{n // 2}.py"
        corpos: list[int] = []
        for k in range(5):
            arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", f"item * {k + 3} * ", 1) if k == 0 else arq.read_text(encoding="utf-8").replace(f"item * {k + 2} * ", f"item * {k + 3} * ", 1), encoding="utf-8")
            rep = index_project(cfg)
            if k == 0:
                print(f"entidades sem chunk_id depois de editar 1 linha, só com o índice: {sem_chunk()}")
            t0 = time.perf_counter()
            g = update_documents(cfg, rep.touched_documents)
            corpos.append(int((time.perf_counter() - t0) * 1000))
            assert not g.fallback_full, g.reason
            if k == 0:
                print(f"entidades sem chunk_id depois do update_documents: {sem_chunk()}")
        mediana = sorted(corpos)[len(corpos) // 2]
        print(f"update_documents, corpo editado (mediana de 5): {mediana} ms = {100 * mediana / max(ms_completo, 1):.1f}% do completo")

        arq.write_text(arq.read_text(encoding="utf-8") + "\n\ndef nova_funcao(x):\n    '''Nova.'''\n    total = x * 2\n    total += x * 3\n    return total + 1\n", encoding="utf-8")
        rep = index_project(cfg)
        t0 = time.perf_counter()
        g = update_documents(cfg, rep.touched_documents)
        print(f"update_documents, símbolo novo (cai no completo={g.fallback_full}): {int((time.perf_counter() - t0) * 1000)} ms")
        os.chdir(origem)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commits", type=int, default=100)
    ap.add_argument("--modulos", type=int, default=400)
    ap.add_argument("--so-tempos", action="store_true")
    args = ap.parse_args()
    if not args.so_tempos:
        fracao_sem_mudanca_de_simbolos(args.commits)
    tempos(args.modulos)


if __name__ == "__main__":
    main()

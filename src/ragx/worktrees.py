"""Worktrees do mesmo repositório e o que eles compartilham (RAGX-0170).

Só metadados e contagens: nenhum conteúdo de arquivo é lido aqui. Cada worktree tem o PRÓPRIO índice
(`<raiz>/.ragx/knowledge.db`); o que é comum é o cache de embedding, em `<pasta .git comum>/ragx/cache`, por
`content_hash` do chunk. Esta função diz, para cada worktree, quantos chunks (conteúdos distintos) ele tem em comum
com o da raiz consultada, que é o que o cache compartilhado poupa de reembutir.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ragx import gitinfo
from ragx.config import Config
from ragx.indexing.embed import shared_cache_root


def _abrir_leitura(banco: Path) -> sqlite3.Connection:
    return sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True, timeout=5.0)


def _contagens(banco: Path, referencia: Path | None) -> dict[str, int] | None:
    """Documentos, chunks distintos e (se `referencia`) quantos desses chunks também estão na referência."""
    if not banco.is_file():
        return None
    try:
        conn = _abrir_leitura(banco)
    except sqlite3.Error:
        return None
    try:
        out = {
            "documents": int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]),
            "chunks": int(conn.execute("SELECT COUNT(DISTINCT content_hash) FROM chunks").fetchone()[0]),
        }
        if referencia is not None and referencia.is_file():
            conn.execute("ATTACH DATABASE ? AS ref", (referencia.as_uri() + "?mode=ro",))
            out["shared_chunks"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM (SELECT content_hash FROM main.chunks INTERSECT "
                    "SELECT content_hash FROM ref.chunks)"
                ).fetchone()[0]
            )
        return out
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _cache_compartilhado(cfg: Config) -> dict[str, Any]:
    raiz = shared_cache_root(cfg)
    arquivos = sorted((raiz / "emb").glob("*.sqlite")) if (raiz / "emb").is_dir() else []
    return {
        "path": raiz.as_posix(),
        "shared": raiz != cfg.state_dir / "cache",
        "models": [a.stem for a in arquivos],
        "size_mb": round(sum(a.stat().st_size for a in arquivos) / 2**20, 1),
    }


def report(cfg: Config) -> dict[str, Any]:
    """Os worktrees do repositório da `cfg.root`, com contagens por índice. Vazio fora de git."""
    lista = gitinfo.worktrees(cfg.root)
    atual = cfg.root.resolve()
    referencia = cfg.db_path
    itens: list[dict[str, Any]] = []
    for w in lista:
        eh_este = w.path.resolve() == atual
        banco = w.path / ".ragx" / "knowledge.db"
        contagens = _contagens(banco, None if eh_este else referencia)
        itens.append({
            "path": w.path.as_posix(),
            "branch": w.branch,
            "head": w.head,
            "detached": w.detached,
            "current": eh_este,
            "indexed": contagens is not None,
            **(contagens or {}),
        })
    return {"worktrees": itens, "embedding_cache": _cache_compartilhado(cfg)}

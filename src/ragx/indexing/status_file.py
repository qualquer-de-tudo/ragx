"""`.ragx/status.json`: o estado do índice num arquivo que qualquer um lê.

O painel e outras ferramentas leem este arquivo em vez de abrir o SQLite.
Escrita atômica (temporário + os.replace) para ninguém ler JSON pela metade.
Só contagens e metadados: nenhum caminho de arquivo do projeto.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.indexing import lock
from ragx.storage.db import open_db, utcnow

STATUS_NAME = "status.json"
SCHEMA = 1


def _default_probe(root: Path) -> bool | None:
    from ragx import githooks  # import tardio: sem ciclo com o pipeline

    return githooks.installed(root)


# Indireção para não importar o módulo de hooks, que conhece o shell, direto
# no topo do arquivo (evita ciclo com o pipeline).
hooks_installed_probe: Callable[[Path], bool | None] = _default_probe


def _last_finished(conn: Any) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM index_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _build(cfg: Config, conn: Any, last_error: str | None) -> dict[str, Any]:
    run = _last_finished(conn)
    documents = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    embeddings = conn.execute(
        "SELECT COUNT(DISTINCT chunk_id) FROM embeddings"
    ).fetchone()[0]
    current = lock.holder(cfg.state_dir)
    pid = current.get("pid") if current else None
    running = current if isinstance(pid, int) and lock.pid_alive(pid) else None
    dirty = run.get("git_dirty") if run else None
    return {
        "schema_version": SCHEMA,
        "written_at": utcnow(),
        "project": {
            "id": cfg.project.id,
            "name": cfg.project.name,
            "root": cfg.root.as_posix(),
        },
        "index": None if run is None else {
            "finished_at": run["finished_at"],
            "mode": run["mode"],
            "source": run.get("source", "cli"),
            "branch": run.get("git_branch"),
            "commit": run.get("git_commit"),
            "dirty": None if dirty is None else bool(dirty),
        },
        "counts": {
            "documents": documents,
            "chunks": chunks,
            "embeddings": embeddings,
            "pending_embeddings": max(chunks - embeddings, 0),
        },
        "embedding": {"provider": cfg.embedding.provider, "model": cfg.embedding.model},
        "hooks": {"installed": hooks_installed_probe(cfg.root)},
        "running": running,
        "pending": lock.is_pending(cfg.state_dir),
        "last_error": last_error if last_error is not None else (run or {}).get("error"),
    }


def write_status(cfg: Config, *, last_error: str | None = None) -> Path | None:
    if not Path(cfg.db_path).exists():
        return None
    try:
        with open_db(cfg.db_path, read_only=True) as conn:
            data = _build(cfg, conn, last_error)
        target = cfg.state_dir / STATUS_NAME
        tmp = cfg.state_dir / f"{STATUS_NAME}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return target
    except Exception:
        # Status é informativo: nunca derruba uma indexação.
        return None

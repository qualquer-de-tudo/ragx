"""O gate em cache do watcher não é um atalho (RAGX-0147): segredo criado depois de muitos ciclos continua bloqueado."""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.storage.db import open_db
from ragx.watch.monitor import watch

pytestmark = pytest.mark.security

SEGREDO = "AKIAIOSFODNN7EXAMPLE"


@pytest.fixture()
def cfg(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "ragx.toml").write_text(
        '[project]\nname = "w"\nid = "w"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n\n'
        "[watch]\ninterval_s = 0.0\ndebounce_s = 0.0\nfull_sync_every = 100\n",
        encoding="utf-8",
    )
    (root / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    c = load_config(root)
    index_project(c)
    return c


def _roda(cfg, escreve) -> None:  # type: ignore[no-untyped-def]
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        ciclo["n"] += 1
        if ciclo["n"] == 50:
            escreve()

    watch(cfg, max_cycles=56, sleep=sleep)


def test_arquivo_com_segredo_criado_no_ciclo_50_nao_entra_no_indice(cfg) -> None:
    _roda(cfg, lambda: (cfg.root / "config.py").write_text(f'KEY = "{SEGREDO}"\n', encoding="utf-8"))
    with open_db(cfg.db_path, read_only=True) as conn:
        docs = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
        assert "config.py" not in docs
        assert not conn.execute("SELECT 1 FROM chunks WHERE content LIKE ?", (f"%{SEGREDO}%",)).fetchone()
        assert not conn.execute("SELECT 1 FROM chunks_fts WHERE chunks_fts MATCH ?", ("AKIAIOSFODNN7EXAMPLE",)).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM security_events").fetchone()[0] >= 1


def test_env_novo_no_ciclo_50_nao_entra_no_indice(cfg) -> None:
    _roda(cfg, lambda: (cfg.root / ".env").write_text("TOKEN=abc123\n", encoding="utf-8"))
    with open_db(cfg.db_path, read_only=True) as conn:
        assert ".env" not in {r[0] for r in conn.execute("SELECT rel_path FROM documents")}

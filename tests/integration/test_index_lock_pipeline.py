from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import IndexBusyError
from ragx.indexing import lock
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _sources(root: Path) -> list[str]:
    conn = sqlite3.connect(root / ".ragx" / "knowledge.db")
    try:
        return [r[0] for r in conn.execute("SELECT source FROM index_runs ORDER BY id")]
    finally:
        conn.close()


def test_ocupado_agenda_e_lanca(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    monkeypatch.setattr(lock, "pid_alive", lambda pid: True)
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / lock.LOCK_NAME).write_text(
        '{"pid": 999999, "op": "index", "source": "watch", "started_at": "x"}', encoding="utf-8"
    )
    with pytest.raises(IndexBusyError) as exc:
        index_project(cfg, source="hook:post-commit")
    assert exc.value.holder["source"] == "watch"
    assert lock.is_pending(cfg.state_dir)


def test_pendencia_faz_o_dono_rodar_de_novo(proj: Path) -> None:
    cfg = load_config(proj)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    lock.mark_pending(cfg.state_dir, "hook:post-merge")
    index_project(cfg, source="cli")
    assert _sources(proj) == ["cli", "hook:post-merge"]
    assert not lock.is_pending(cfg.state_dir)
    assert lock.holder(cfg.state_dir) is None


def test_trava_e_liberada_mesmo_com_erro(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ragx.indexing.pipeline as pipeline

    cfg = load_config(proj)

    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("falhou")

    monkeypatch.setattr(pipeline, "_index_once", boom)
    with pytest.raises(RuntimeError):
        index_project(cfg)
    assert lock.holder(cfg.state_dir) is None


def test_dry_run_nao_toca_na_trava(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    monkeypatch.setattr(lock, "try_acquire", lambda *a: pytest.fail("dry-run pegou a trava"))
    index_project(cfg, dry_run=True)

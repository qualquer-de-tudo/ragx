from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from ragx.config import load_config
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


def _last_run(root: Path) -> sqlite3.Row:
    conn = sqlite3.connect(root / ".ragx" / "knowledge.db")
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM index_runs ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()


def test_sem_git_grava_origem_e_git_nulo(proj: Path) -> None:
    index_project(load_config(proj), source="panel")
    run = _last_run(proj)
    assert run["source"] == "panel"
    assert run["git_branch"] is None and run["git_commit"] is None and run["git_dirty"] is None


def test_com_git_grava_branch_e_commit(proj: Path) -> None:
    if subprocess.run(["git", "init", "-q", "-b", "feat/x"], cwd=proj).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=proj, check=True)
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=proj, check=True)
    index_project(load_config(proj))
    run = _last_run(proj)
    assert run["source"] == "cli"
    assert run["git_branch"] == "feat/x"
    assert len(run["git_commit"]) == 40
    assert run["git_dirty"] in (0, 1)


def test_embed_only_tem_modo_proprio_e_conta_vetores(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    index_project(cfg, embed_only=True)
    run = _last_run(proj)
    assert run["mode"] == "embed-only"
    assert run["embedded"] > 0


def test_origem_invalida_e_recusada(proj: Path) -> None:
    from ragx.core.errors import UsageError

    with pytest.raises(UsageError):
        index_project(load_config(proj), source="qualquer")


def test_recent_devolve_mais_novo_primeiro(proj: Path) -> None:
    from ragx.storage.db import open_db
    from ragx.storage.repositories import RunRepo

    cfg = load_config(proj)
    index_project(cfg, source="cli")
    index_project(cfg, source="watch")
    with open_db(cfg.db_path) as conn:
        runs = RunRepo(conn).recent(10)
    assert [r["source"] for r in runs[:2]] == ["watch", "cli"]

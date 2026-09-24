"""`ragx runs`: histórico de indexações paginado, para a linha do tempo do painel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.config import load_config
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.e2e
runner = CliRunner()


@pytest.fixture()
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    for _ in range(3):
        index_project(cfg)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_pagina_do_mais_novo_para_o_mais_antigo(proj: Path) -> None:
    p1 = json.loads(runner.invoke(app, ["runs", "--limit", "2", "--json"]).output)
    p2 = json.loads(runner.invoke(app, ["runs", "--limit", "2", "--offset", "2", "--json"]).output)
    assert p1["total"] == 3
    assert len(p1["runs"]) == 2 and len(p2["runs"]) == 1
    ids = [r["id"] for r in p1["runs"] + p2["runs"]]
    assert ids == sorted(ids, reverse=True)


def test_sem_indice_devolve_vazio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["runs", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"runs": [], "total": 0, "offset": 0, "limit": 10}

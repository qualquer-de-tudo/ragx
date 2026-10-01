"""`ragx sync` num clone novo, sem `.ragx/` (RAGX-0144): falhava com "banco não encontrado"."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.config import load_config
from ragx.sync.service import sync

pytestmark = pytest.mark.e2e
runner = CliRunner()

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    origem = tmp_path / "origem"
    origem.mkdir()
    (origem / "ragx.toml").write_text(TOML, encoding="utf-8")
    (origem / "a.py").write_text("def autenticar(usuario):\n    return usuario\n", encoding="utf-8")
    sync(load_config(origem))
    destino = tmp_path / "clone"
    shutil.copytree(origem, destino, ignore=shutil.ignore_patterns(".ragx"))
    return destino


def test_sync_em_clone_sem_banco_sai_com_zero_e_a_busca_responde(clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(clone)
    assert not (clone / ".ragx").exists()
    r = runner.invoke(app, ["sync"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["search", "autenticar usuario", "--mode", "keyword", "--json"])
    assert r.exit_code == 0, r.output
    assert "a.py" in r.output


def test_busca_sem_banco_mas_com_knowledge_manda_rodar_sync(clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(clone)
    r = runner.invoke(app, ["search", "autenticar"])
    assert r.exit_code != 0
    assert "ragx sync" in (r.output + str(r.exception or ""))

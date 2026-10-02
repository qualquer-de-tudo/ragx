"""`ragx context` sem `--tokens` (RAGX-0150)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app

pytestmark = pytest.mark.e2e
runner = CliRunner()


@pytest.fixture()
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "c"\nid = "c"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "gate.py").write_text("def decide_bloqueio(arquivo):\n    return arquivo.endswith('.env')\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["index", "."])
    return tmp_path


def test_sem_tokens_sai_com_zero_e_usa_o_padrao(projeto: Path) -> None:
    r = runner.invoke(app, ["context", "como o gate decide bloqueio", "--format", "json"])
    assert r.exit_code == 0, r.output


def test_tokens_abaixo_do_minimo_continua_recusado(projeto: Path) -> None:
    assert runner.invoke(app, ["context", "x", "--tokens", "100"]).exit_code != 0

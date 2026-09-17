from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.config import load_config

pytestmark = pytest.mark.e2e

runner = CliRunner()


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text(
        'class AuthService:\n    """Login via SSO."""\n    def login(self):\n        pass\n',
        encoding="utf-8",
    )
    (tmp_path / "queries.yaml").write_text(
        "- query: autenticacao\n  relevant_paths: [\"auth.py\"]\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    return tmp_path


def test_trial_json_reports_savings(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["trial", "--queries", "queries.yaml", "--json"])
    assert result.exit_code == 0, result.output
    assert '"baseline_tokens"' in result.output
    assert '"ragx_tokens"' in result.output
    assert '"caveat"' in result.output


def test_trial_human_output_prints_honesty_caveat(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["trial", "--queries", "queries.yaml"])
    assert result.exit_code == 0, result.output
    assert "proxy" in result.output.lower()

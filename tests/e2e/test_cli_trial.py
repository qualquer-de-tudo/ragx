from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.config import load_config
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project

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


def test_trial_human_output_escapes_rich_markup_in_query(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão: `[project]`/`[/bold]` numa query não pode virar tag de markup
    do Rich — nem some silenciosamente (corrompendo a tabela), nem estoura
    `rich.errors.MarkupError` (crash com traceback cru)."""
    monkeypatch.chdir(proj)
    (proj / "queries.yaml").write_text(
        '- query: "query with [brackets] inside"\n  relevant_paths: []\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["trial", "--queries", "queries.yaml"])
    assert result.exit_code == 0, result.output
    assert "query with [brackets] inside" in result.output


def test_trial_sem_queries_gera_consultas_do_indice(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.chdir(proj)
    r = runner.invoke(app, ["trial", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados["auto_generated"] is True
    assert dados["cases"] >= 1
    assert dados["results"][0]["query"].startswith("como funciona")


def test_trial_com_queries_explicito_inexistente_continua_erro(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(proj)
    r = runner.invoke(app, ["trial", "--queries", "nao-existe.yaml", "--json"])
    assert r.exit_code != 0


def test_trial_sem_grafo_usa_nomes_de_arquivo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    corpo = "\n".join(f"export const valor{i} = {i}" for i in range(120))
    (tmp_path / "billing-orders.ts").write_text(corpo, encoding="utf-8")
    index_project(load_config(tmp_path))  # sem rebuild: grafo vazio
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["trial", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert [x["query"] for x in dados["results"]] == ["como funciona billing-orders"]

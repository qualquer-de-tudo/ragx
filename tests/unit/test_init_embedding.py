"""`ragx init` escolhe o embedding ao criar o projeto (RAGX-0204)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.commands import init as init_cmd
from ragx.cli.main import app

pytestmark = pytest.mark.unit
runner = CliRunner()


@pytest.fixture()
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("RAGX_EMBEDDING_PROVIDER", raising=False)
    raiz = tmp_path / "proj"
    raiz.mkdir()
    return raiz


def _provider(raiz: Path) -> str | None:
    dados = tomllib.loads((raiz / "ragx.toml").read_text(encoding="utf-8"))
    return dados.get("embedding", {}).get("provider")


@pytest.mark.parametrize(
    ("ollama", "fastembed", "esperado"),
    [(True, True, "ollama"), (False, True, "fastembed"), (None, True, "fastembed"), (None, False, "ollama")],
)
def test_escolhe_pelo_que_a_maquina_tem(
    projeto: Path, monkeypatch: pytest.MonkeyPatch, ollama: bool | None, fastembed: bool, esperado: str
) -> None:
    monkeypatch.setattr(init_cmd, "_ollama_tem", lambda *a, **k: ollama)
    monkeypatch.setattr(init_cmd, "_tem_fastembed", lambda: fastembed)
    r = runner.invoke(app, ["init", str(projeto)])
    assert r.exit_code == 0, r.output
    assert _provider(projeto) == esperado
    assert "embedding:" in r.output


def test_opcao_forca_e_valor_invalido_e_recusado(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(init_cmd, "_ollama_tem", lambda *a, **k: True)
    assert runner.invoke(app, ["init", str(projeto), "--embedding", "fastembed"]).exit_code == 0
    assert _provider(projeto) == "fastembed"
    r = runner.invoke(app, ["init", str(projeto), "--force", "--embedding", "openai"])
    assert r.exit_code != 0


def test_ambiente_ja_escolheu_e_nada_e_gravado(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAGX_EMBEDDING_PROVIDER", "hashing")
    assert runner.invoke(app, ["init", str(projeto)]).exit_code == 0
    assert _provider(projeto) is None


def test_projeto_com_ragx_toml_nao_muda(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (projeto / "ragx.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    monkeypatch.setattr(init_cmd, "_ollama_tem", lambda *a, **k: None)
    runner.invoke(app, ["init", str(projeto)])
    assert (projeto / "ragx.toml").read_text(encoding="utf-8") == '[project]\nname = "x"\n'

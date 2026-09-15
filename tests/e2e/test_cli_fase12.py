"""E2E da Fase 12: `ragx base`, `ragx watch`, `ragx --version`.

Existe porque um bug de formatação escapou de 600 testes: `ragx base list`
estourava o parser de markup do Rich e nada pegava, já que a suíte chamava as
funções por baixo e nunca a CLI. Aqui os comandos são EXECUTADOS.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app

pytestmark = pytest.mark.e2e
runner = CliRunner()

REGRA = """# Guardrails

O agente NUNCA executa migracao de banco sem aprovacao explicita do humano.
"""


@pytest.fixture
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("RAGX_EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setenv("RAGX_EMBEDDING_DIM", "128")
    monkeypatch.setenv("RAGX_EMBEDDING_VERSIONED_DIM", "64")
    monkeypatch.setenv("RAGX_HUB_PATH", str(home / ".ragx" / "hub"))

    fonte = tmp_path / "regras"
    fonte.mkdir()
    (fonte / "guardrails.md").write_text(REGRA, encoding="utf-8")

    raiz = tmp_path / "proj"
    raiz.mkdir()
    (raiz / "app.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(raiz)
    assert runner.invoke(app, ["init", "."]).exit_code == 0
    return raiz, fonte


def test_version_em_flag_e_em_comando() -> None:
    for args in (["--version"], ["version"]):
        r = runner.invoke(app, args)
        assert r.exit_code == 0, r.output
        assert r.output.startswith("ragx "), r.output


def test_sem_argumento_mostra_ajuda() -> None:
    r = runner.invoke(app, [])
    assert r.exit_code == 0
    assert "Usage" in r.output


def test_base_list_vazio_orienta(projeto: tuple[Path, Path]) -> None:
    r = runner.invoke(app, ["base", "list"])
    assert r.exit_code == 0, r.output
    assert "ragx base add" in r.output


def test_ciclo_completo_de_base(projeto: tuple[Path, Path]) -> None:
    raiz, fonte = projeto

    r = runner.invoke(app, ["base", "add", str(fonte), "--name", "casa"])
    assert r.exit_code == 0, r.output
    assert "casa" in r.output

    # `--declare` (padrão) grava no ragx.toml — sem isso nada seria indexado.
    toml = (raiz / "ragx.toml").read_text(encoding="utf-8")
    assert "[base]" in toml and "sources" in toml

    r = runner.invoke(app, ["base", "list"])
    assert r.exit_code == 0, r.output
    assert "casa" in r.output

    r = runner.invoke(app, ["base", "list", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados["sources"][0]["name"] == "casa"

    r = runner.invoke(app, ["search", "migracao de banco aprovacao", "--mode", "keyword"])
    assert r.exit_code == 0, r.output
    assert "@base/casa" in r.output, r.output

    r = runner.invoke(app, ["base", "disable", "casa"])
    assert r.exit_code == 0, r.output
    assert runner.invoke(app, ["index", "."]).exit_code == 0

    r = runner.invoke(app, ["base", "remove", "casa", "--yes"])
    assert r.exit_code == 0, r.output


def test_base_add_sem_declarar_avisa_que_nao_indexa(projeto: tuple[Path, Path]) -> None:
    _raiz, fonte = projeto
    r = runner.invoke(app, ["base", "add", str(fonte), "--name", "x", "--no-declare"])
    assert r.exit_code == 0, r.output
    assert "não declarada" in r.output


def test_base_remove_inexistente_e_erro_de_uso(projeto: tuple[Path, Path]) -> None:
    r = runner.invoke(app, ["base", "remove", "nao-existe", "--yes"])
    assert r.exit_code != 0


def test_watch_once(projeto: tuple[Path, Path]) -> None:
    raiz, _fonte = projeto
    (raiz / "novo.py").write_text("def novo():\n    return 2\n", encoding="utf-8")

    r = runner.invoke(app, ["watch", "--once"])
    assert r.exit_code == 0, r.output
    assert "reindexado" in r.output

    r = runner.invoke(app, ["documents"])
    assert "novo.py" in r.output


def test_watch_once_plain_sai_em_json(projeto: tuple[Path, Path]) -> None:
    r = runner.invoke(app, ["watch", "--once", "--plain"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["error"] is None


def test_watch_sem_indice_orienta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    monkeypatch.chdir(vazio)
    r = runner.invoke(app, ["watch"])
    assert r.exit_code == 1
    assert "ragx init" in r.output


def test_curinga_nao_e_expandido_contra_o_diretorio_atual(
    projeto: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--path "*src*"` é um PADRÃO, não uma lista de arquivos.

    No Windows o Click reescreve os argumentos antes de entregá-los ao comando
    (`windows_expand_args=True`, o padrão): ele roda `glob` em cada um e troca
    pelo que casar no diretório atual. Medido neste repositório: `--path
    "*ragx*"` chegava como `ragx.toml` — um arquivo — e a listagem devolvia um
    documento só; `--path "*src*"` virava `src` e devolvia zero.

    O mesmo comando dava resultados diferentes conforme o que existisse na
    pasta. Este teste PRECISA rodar a CLI como processo: o `CliRunner` chama o
    Click por dentro e nunca passa pela expansão — foi por isso que o bug
    sobreviveu à suíte inteira.
    """
    import subprocess
    import sys

    raiz, _fonte = projeto
    # A isca: uma pasta com o nome que o curinga casaria.
    (raiz / "src").mkdir()
    (raiz / "src" / "servico.py").write_text("def s():\n    return 1\n", encoding="utf-8")
    assert runner.invoke(app, ["index", "."]).exit_code == 0

    saida = subprocess.run(
        [sys.executable, "-m", "ragx.cli.main",
         "documents", "--path", "*src*", "--limit", "50", "--json"],
        capture_output=True, cwd=raiz, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    caminhos = [d["rel_path"] for d in json.loads(saida.stdout.decode("utf-8"))]
    assert "src/servico.py" in caminhos, (
        f"o curinga foi expandido contra o disco: {caminhos}"
    )

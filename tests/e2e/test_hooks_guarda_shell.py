"""A guarda de shell do `post-checkout`: arquivo não sobe Python nenhum (RAGX-0143)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx import githooks
from ragx.cli.main import app

pytestmark = pytest.mark.e2e
runner = CliRunner()


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")
    (tmp_path / "a.txt").write_text("um\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "inicial")
    return tmp_path


def _stub(tmp_path: Path) -> tuple[str, Path]:
    """Um `ragx` falso que só grava um marcador: prova se o hook CHEGOU a rodar o executável."""
    marcador = tmp_path / "chamadas.txt"
    stub = tmp_path / "stub.sh"
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{marcador.as_posix()}"\n', encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    return f'"{stub.as_posix()}"', marcador


def _chamadas(marcador: Path) -> list[str]:
    return marcador.read_text(encoding="utf-8").splitlines() if marcador.exists() else []


def test_o_bloco_de_post_checkout_traz_a_guarda_e_os_outros_nao(repo: Path) -> None:
    githooks.install(repo, '"/x/ragx"')
    hooks = repo / ".git" / "hooks"
    assert '[ "$3" = "1" ]' in (hooks / "post-checkout").read_text(encoding="utf-8")
    assert '"$3"' not in (hooks / "post-commit").read_text(encoding="utf-8")
    assert '"$3"' not in (hooks / "post-merge").read_text(encoding="utf-8")


def test_checkout_de_arquivo_nao_roda_o_executavel_e_troca_de_branch_roda(repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    prefixo, marcador = _stub(tmp_path_factory.mktemp("stub"))
    githooks.install(repo, prefixo)

    (repo / "a.txt").write_text("dois\n", encoding="utf-8")
    _git(repo, "checkout", "--", "a.txt")  # checkout de ARQUIVO ($3 = 0)
    assert _chamadas(marcador) == []

    _git(repo, "checkout", "-q", "-b", "outra")  # troca de branch ($3 = 1)
    assert len(_chamadas(marcador)) == 1 and "hook-run post-checkout" in _chamadas(marcador)[0]


def test_skip_hook_continua_valendo(repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    prefixo, marcador = _stub(tmp_path_factory.mktemp("stub"))
    githooks.install(repo, prefixo)
    monkeypatch.setenv("RAGX_SKIP_HOOK", "1")
    _git(repo, "checkout", "-q", "-b", "outra")
    assert _chamadas(marcador) == []


def test_instalar_sobre_bloco_antigo_o_substitui_sem_duplicar_e_status_acusa(repo: Path) -> None:
    githooks.install(repo, '"/x/ragx"')
    hook = repo / ".git" / "hooks" / "post-checkout"
    # volta ao formato antigo: sem a guarda
    hook.write_text(
        hook.read_text(encoding="utf-8").replace(' && [ "$3" = "1" ]', ""), encoding="utf-8", newline="\n"
    )
    assert githooks.state(repo)["outdated"] == ["post-checkout"]
    r = runner.invoke(app, ["hooks", "status", str(repo)])
    assert "formato antigo" in r.output and "ragx hooks install" in r.output

    githooks.install(repo, '"/x/ragx"')
    corpo = hook.read_text(encoding="utf-8")
    assert corpo.count("ragx-hook-start") == 1 and '[ "$3" = "1" ]' in corpo
    assert githooks.state(repo)["outdated"] == []
    assert githooks.state(repo)["installed"] is True


def test_bloco_atual_nao_e_acusado_como_antigo(repo: Path) -> None:
    githooks.install(repo, '"/x/ragx"')
    assert githooks.state(repo)["outdated"] == []

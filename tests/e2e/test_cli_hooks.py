from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app

runner = CliRunner()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")
    return tmp_path


def test_install_status_uninstall(repo: Path) -> None:
    r = runner.invoke(app, ["hooks", "install", str(repo)])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["hooks", "status", str(repo), "--json"])
    assert json.loads(r.output)["installed"] is True
    r = runner.invoke(app, ["hooks", "uninstall", str(repo)])
    assert r.exit_code == 0
    r = runner.invoke(app, ["hooks", "status", str(repo), "--json"])
    assert json.loads(r.output)["installed"] is False


def test_hook_run_ignora_checkout_de_arquivo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx import githooks

    calls: list[str] = []
    monkeypatch.setattr(githooks, "spawn_index", lambda root, ev: calls.append(ev))
    r = runner.invoke(app, ["hook-run", "post-checkout", "--root", str(repo), "a", "b", "0"])
    assert r.exit_code == 0 and calls == []
    r = runner.invoke(app, ["hook-run", "post-checkout", "--root", str(repo), "a", "b", "1"])
    assert r.exit_code == 0 and calls == ["post-checkout"]


def test_hook_run_evento_desconhecido_sai_quieto(repo: Path) -> None:
    r = runner.invoke(app, ["hook-run", "pre-push", "--root", str(repo)])
    assert r.exit_code == 0


def test_init_git_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    # Isola o HOME: `ragx init` registra o projeto no hub local (~/.ragx/hub);
    # sem isso este teste vazaria um projeto extra no hub compartilhado da
    # sessão e quebraria testes de outros módulos que esperam um hub limpo.
    fake_home = tmp_path.parent / f"{tmp_path.name}-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    r = runner.invoke(app, ["init", str(tmp_path), "--git-hooks"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".git" / "hooks" / "post-commit").exists()

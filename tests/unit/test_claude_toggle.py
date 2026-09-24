"""`ragx claude on|off|status`: liga e desliga o RAGX no Claude Code, global."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.clients.registry import CLIENTS, is_registered

pytestmark = pytest.mark.unit
runner = CliRunner()


@pytest.fixture()
def casa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _config(home: Path) -> Path:
    return home / ".claude.json"


def _claude_code():
    return next(c for c in CLIENTS() if c.id == "claude-code")


def test_off_remove_so_o_ragx_e_on_devolve(casa: Path) -> None:
    _config(casa).write_text(
        json.dumps({"mcpServers": {"outro": {"command": "x"}}, "theme": "dark"}), encoding="utf-8"
    )
    assert not is_registered(_claude_code())

    r = runner.invoke(app, ["claude", "on"])
    assert r.exit_code == 0, r.output
    assert is_registered(_claude_code())

    r = runner.invoke(app, ["claude", "off"])
    assert r.exit_code == 0, r.output
    assert not is_registered(_claude_code())
    dados = json.loads(_config(casa).read_text(encoding="utf-8"))
    assert dados["mcpServers"] == {"outro": {"command": "x"}}
    assert dados["theme"] == "dark"


def test_status_diz_ligado_ou_desligado(casa: Path) -> None:
    _config(casa).write_text("{}", encoding="utf-8")
    off = runner.invoke(app, ["claude", "status", "--json"])
    assert json.loads(off.output)["enabled"] is False
    runner.invoke(app, ["claude", "on"])
    on = runner.invoke(app, ["claude", "status", "--json"])
    assert json.loads(on.output)["enabled"] is True


def test_on_e_off_sao_idempotentes(casa: Path) -> None:
    _config(casa).write_text("{}", encoding="utf-8")
    assert runner.invoke(app, ["claude", "off"]).exit_code == 0
    assert runner.invoke(app, ["claude", "on"]).exit_code == 0
    assert runner.invoke(app, ["claude", "on"]).exit_code == 0
    assert is_registered(_claude_code())


def test_json_quebrado_nao_e_sobrescrito(casa: Path) -> None:
    _config(casa).write_text("{quebrado", encoding="utf-8")
    r = runner.invoke(app, ["claude", "on"])
    assert r.exit_code == 1
    assert _config(casa).read_text(encoding="utf-8") == "{quebrado"


def test_on_e_off_json_para_o_painel(casa: Path) -> None:
    _config(casa).write_text("{}", encoding="utf-8")
    on = runner.invoke(app, ["claude", "on", "--json"])
    assert on.exit_code == 0, on.output
    assert json.loads(on.output) == {"enabled": True, "changed": True, "detail": json.loads(on.output)["detail"]}
    off = runner.invoke(app, ["claude", "off", "--json"])
    dados = json.loads(off.output)
    assert dados["enabled"] is False and dados["changed"] is True
    de_novo = json.loads(runner.invoke(app, ["claude", "off", "--json"]).output)
    assert de_novo["enabled"] is False and de_novo["changed"] is False


def test_falha_em_json_traz_error_e_sai_1(casa: Path) -> None:
    _config(casa).write_text("{quebrado", encoding="utf-8")
    r = runner.invoke(app, ["claude", "on", "--json"])
    assert r.exit_code == 1
    assert "error" in json.loads(r.output)

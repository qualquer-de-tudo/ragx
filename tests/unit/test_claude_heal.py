"""`ragx claude heal`: completa os hooks que faltam, só onde o RAGX já está ligado, e respeita a recusa."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.clients.claude_heal import optout_of
from ragx.clients.claude_hint import has_hint, has_nudge_hook, has_touch_hook
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


def _padrao():
    return next(c for c in CLIENTS() if c.id == "claude-code")


def _ligar_so_o_mcp_e_a_dica() -> None:
    """O estado de quem ligou numa versão antiga: MCP e dica, sem o aviso de edição nem o lembrete."""
    r = runner.invoke(app, ["claude", "on", "--no-touch", "--no-nudge"])
    assert r.exit_code == 0, r.output


def test_heal_instala_o_que_faltava_em_perfil_ligado(casa: Path) -> None:
    _ligar_so_o_mcp_e_a_dica()
    # Quem ligou numa versão antiga não tinha recusado nada: a recusa gravada pelo `on` não vale.
    (casa / ".ragx" / "claude-optout.json").unlink()
    assert not has_touch_hook(_padrao()) and not has_nudge_hook(_padrao())

    r = runner.invoke(app, ["claude", "heal", "--json"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["changed"] is True
    assert sorted(out["healed"][0]["installed"]) == ["nudge", "touch"]
    assert has_touch_hook(_padrao()) and has_nudge_hook(_padrao()) and has_hint(_padrao())


def test_heal_e_idempotente(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    r = runner.invoke(app, ["claude", "heal", "--json"])
    assert json.loads(r.output)["changed"] is False


def test_heal_completa_subagentstart_sem_alterar_hook_alheio(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    settings = casa / ".claude" / "settings.json"
    dados = json.loads(settings.read_text(encoding="utf-8"))
    alheio = {"hooks": [{"type": "command", "command": "echo subagente"}]}
    dados["hooks"]["SubagentStart"] = [alheio]
    settings.write_text(json.dumps(dados), encoding="utf-8")
    assert not has_hint(_padrao())
    r = runner.invoke(app, ["claude", "heal", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["healed"][0]["installed"] == ["hint"]
    assert has_hint(_padrao())
    assert alheio in json.loads(settings.read_text(encoding="utf-8"))["hooks"]["SubagentStart"]
    runner.invoke(app, ["claude", "off"])
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"]["SubagentStart"] == [alheio]


def test_heal_nao_liga_um_perfil_desligado(casa: Path) -> None:
    r = runner.invoke(app, ["claude", "heal", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["changed"] is False
    assert not is_registered(_padrao())
    assert not has_touch_hook(_padrao())


def test_heal_respeita_o_no_touch_escolhido_de_proposito(casa: Path) -> None:
    _ligar_so_o_mcp_e_a_dica()
    assert optout_of("claude-code") == {"touch", "nudge"}
    r = runner.invoke(app, ["claude", "heal", "--json"])
    out = json.loads(r.output)
    assert out["changed"] is False
    assert sorted(out["healed"][0]["skipped"]) == ["nudge", "touch"]
    assert not has_touch_hook(_padrao())


def test_on_sem_flags_limpa_a_recusa_e_instala_tudo(casa: Path) -> None:
    _ligar_so_o_mcp_e_a_dica()
    runner.invoke(app, ["claude", "on"])
    assert optout_of("claude-code") == set()
    assert has_touch_hook(_padrao()) and has_nudge_hook(_padrao())


def test_heal_preserva_os_hooks_da_pessoa(casa: Path) -> None:
    runner.invoke(app, ["claude", "on", "--no-touch"])
    (casa / ".ragx" / "claude-optout.json").unlink()
    cfg = casa / ".claude" / "settings.json"
    dados = json.loads(cfg.read_text(encoding="utf-8"))
    dados.setdefault("hooks", {}).setdefault("PostToolUse", []).append(
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "node format.mjs"}]}
    )
    cfg.write_text(json.dumps(dados), encoding="utf-8")

    runner.invoke(app, ["claude", "heal"])
    depois = json.loads(cfg.read_text(encoding="utf-8"))["hooks"]["PostToolUse"]
    comandos = [h["command"] for g in depois for h in g["hooks"]]
    assert "node format.mjs" in comandos
    assert any("touch --stdin-json" in c for c in comandos)


def test_heal_usa_o_executavel_pedido(casa: Path) -> None:
    runner.invoke(app, ["claude", "on", "--no-touch"])
    (casa / ".ragx" / "claude-optout.json").unlink()
    runner.invoke(app, ["claude", "heal", "--command", "C:/ragx/ragx.exe"])
    texto = (casa / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "C:/ragx/ragx.exe" in texto and "touch --stdin-json" in texto

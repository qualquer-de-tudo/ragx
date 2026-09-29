"""Perfis do Claude Code (`CLAUDE_CONFIG_DIR`) e a dica de início de sessão."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.clients.claude_hint import hint_command, hint_text
from ragx.clients.registry import CLIENTS, is_registered

pytestmark = pytest.mark.unit
runner = CliRunner()


@pytest.fixture()
def casa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def _perfil(home: Path, nome: str) -> Path:
    pasta = home / f".claude-{nome}"
    pasta.mkdir()
    (pasta / ".claude.json").write_text(json.dumps({"mcpServers": {"outro": {"command": "x"}}}), encoding="utf-8")
    return pasta


def _ids() -> list[str]:
    return [c.id for c in CLIENTS() if c.id.startswith("claude-code")]


def _hooks(settings: Path) -> list[dict]:
    dados = json.loads(settings.read_text(encoding="utf-8"))
    return [h for g in dados["hooks"]["SessionStart"] for h in g["hooks"]]


# ── perfis ──────────────────────────────────────────────────────────────
def test_perfil_separado_e_descoberto_so_com_claude_json(casa: Path) -> None:
    _perfil(casa, "empresa")
    (casa / ".claude-lixo").mkdir()  # sem .claude.json: nunca foi usado pelo Claude Code
    assert _ids() == ["claude-code", "claude-code:empresa"]


def test_claude_config_dir_conta_mesmo_fora_do_padrao(casa: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outra = tmp_path / "contas" / "cliente"
    outra.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(outra))
    assert _ids() == ["claude-code", "claude-code:cliente"]


def test_on_e_off_valem_para_todos_os_perfis(casa: Path) -> None:
    empresa = _perfil(casa, "empresa")
    r = runner.invoke(app, ["claude", "on", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados["enabled"] is True
    assert {p["id"]: p["enabled"] for p in dados["profiles"]} == {"claude-code": True, "claude-code:empresa": True}
    # o servidor que já estava no perfil da empresa continua lá
    assert "outro" in json.loads((empresa / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]

    r = runner.invoke(app, ["claude", "off", "--json"])
    assert r.exit_code == 0, r.output
    assert not any(is_registered(c) for c in CLIENTS() if c.id.startswith("claude-code"))


def test_status_so_diz_ligado_se_todos_os_perfis_estao(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    _perfil(casa, "empresa")  # perfil novo, criado depois de ligar
    dados = json.loads(runner.invoke(app, ["claude", "status", "--json"]).output)
    assert dados["enabled"] is False
    assert {p["id"]: p["enabled"] for p in dados["profiles"]} == {"claude-code": True, "claude-code:empresa": False}


def test_mcp_install_claude_code_cobre_os_perfis(casa: Path) -> None:
    _perfil(casa, "empresa")
    r = runner.invoke(app, ["mcp", "install", "--client", "claude-code"])
    assert r.exit_code == 0, r.output
    assert all(is_registered(c) for c in CLIENTS() if c.id.startswith("claude-code"))


# ── hook ────────────────────────────────────────────────────────────────
def test_on_instala_a_dica_no_settings_de_cada_perfil(casa: Path) -> None:
    empresa = _perfil(casa, "empresa")
    assert runner.invoke(app, ["claude", "on"]).exit_code == 0
    for settings in (casa / ".claude" / "settings.json", empresa / "settings.json"):
        assert _hooks(settings) == [{"type": "command", "command": "ragx claude hint", "timeout": 15}]


def test_dica_preserva_hooks_da_pessoa_e_e_idempotente(casa: Path) -> None:
    settings = casa / ".claude" / "settings.json"
    alheio = {"type": "command", "command": "echo oi"}
    settings.write_text(
        json.dumps({"theme": "dark", "hooks": {"SessionStart": [{"hooks": [alheio]}], "Stop": [{"hooks": []}]}}),
        encoding="utf-8",
    )
    runner.invoke(app, ["claude", "on"])
    runner.invoke(app, ["claude", "on"])
    assert len(_hooks(settings)) == 2

    runner.invoke(app, ["claude", "off"])
    dados = json.loads(settings.read_text(encoding="utf-8"))
    assert dados["theme"] == "dark"
    assert dados["hooks"] == {"SessionStart": [{"hooks": [alheio]}], "Stop": [{"hooks": []}]}


def test_off_tira_o_bloco_hooks_que_so_tinha_a_dica(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    runner.invoke(app, ["claude", "off"])
    assert "hooks" not in json.loads((casa / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_no_hint_nao_toca_no_settings(casa: Path) -> None:
    assert runner.invoke(app, ["claude", "on", "--no-hint"]).exit_code == 0
    assert not (casa / ".claude" / "settings.json").exists()


def test_settings_quebrado_nao_e_sobrescrito(casa: Path) -> None:
    settings = casa / ".claude" / "settings.json"
    settings.write_text("{quebrado", encoding="utf-8")
    r = runner.invoke(app, ["claude", "on"])
    assert r.exit_code == 1
    assert settings.read_text(encoding="utf-8") == "{quebrado"


def test_comando_absoluto_vai_com_barras_normais_e_aspas() -> None:
    assert hint_command(r"C:\Users\x\.local\bin\ragx.exe") == '"C:/Users/x/.local/bin/ragx.exe" claude hint'
    assert hint_command("ragx") == "ragx claude hint"


# ── texto ───────────────────────────────────────────────────────────────
def _indexado(raiz: Path, nome: str) -> Path:
    (raiz / ".ragx").mkdir(parents=True)
    (raiz / ".ragx" / "knowledge.db").write_bytes(b"")
    (raiz / "ragx.toml").write_text(f'[project]\nname = "{nome}"\n', encoding="utf-8")
    (raiz / ".ragx" / "status.json").write_text(
        json.dumps({"counts": {"documents": 42}, "index": {"finished_at": "2026-09-29T12:00:00Z", "branch": "main"}}),
        encoding="utf-8",
    )
    return raiz


def test_dica_em_projeto_indexado(tmp_path: Path) -> None:
    projeto = _indexado(tmp_path / "loja", "loja")
    (projeto / "src").mkdir()
    texto = hint_text(projeto / "src")  # sessão aberta numa subpasta
    assert "(loja)" in texto and "42 documentos" in texto and "branch main" in texto
    assert "build_context" in texto and "ToolSearch" in texto


def test_dica_calada_fora_de_projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAGX_HUB_PATH", str(tmp_path / "hub"))
    assert hint_text(tmp_path) == ""


def test_dica_na_pasta_pai_aponta_o_scope_de_cada_projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mono = tmp_path / "mono"
    front = _indexado(mono / "frontend", "frontend")
    back = _indexado(mono / "backend" / "src", "api")
    fora = _indexado(tmp_path / "outro", "outro")
    hub = tmp_path / "hub"
    hub.mkdir()
    (hub / "registry.json").write_text(
        json.dumps({"projects": [{"name": n, "path": str(p)} for n, p in (("frontend", front), ("api", back), ("outro", fora))]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAGX_HUB_PATH", str(hub))
    texto = hint_text(mono)
    assert 'backend/src: scope="project:api"' in texto
    assert 'frontend: scope="project:frontend"' in texto
    assert "outro" not in texto


def test_comando_hint_escreve_no_stdout_e_nunca_falha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    projeto = _indexado(tmp_path / "loja", "loja")
    monkeypatch.chdir(projeto)
    r = runner.invoke(app, ["claude", "hint"])
    assert r.exit_code == 0
    assert "RAGX: este projeto (loja)" in r.output

    monkeypatch.setattr("ragx.clients.claude_hint.hint_text", lambda *a, **k: 1 / 0)
    r = runner.invoke(app, ["claude", "hint"])
    assert r.exit_code == 0 and r.output == ""

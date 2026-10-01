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
    assert runner.invoke(app, ["claude", "on", "--no-hint", "--no-touch"]).exit_code == 0
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
    assert "projeto loja indexado" in texto and "documentos" not in texto  # sem o resumo do índice (RAGX-0164)
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
    assert "RAGX: projeto loja indexado" in r.output

    monkeypatch.setattr("ragx.hooklight.texto_projeto", lambda *a, **k: 1 / 0)
    r = runner.invoke(app, ["claude", "hint"])
    assert r.exit_code == 0 and r.output == ""


# ── perfis adicionados à mão e --profile (RAGX-0128) ────────────────────
def test_pasta_adicionada_entra_na_lista_e_liga_so_ela(casa: Path, tmp_path: Path) -> None:
    empresa = _perfil(casa, "empresa")
    outra = tmp_path / "contas" / "cliente"
    outra.mkdir(parents=True)

    r = runner.invoke(app, ["claude", "profiles", "add", str(outra), "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados["changed"] is True
    perfil = next(p for p in dados["profiles"] if p["name"] == "cliente")
    assert perfil["added"] is True and perfil["enabled"] is False

    r = runner.invoke(app, ["claude", "on", "--profile", "cliente", "--json"])
    assert r.exit_code == 0, r.output
    estado = {p["name"]: p for p in json.loads(r.output)["profiles"]}
    assert estado["cliente"]["enabled"] and estado["cliente"]["hint"]
    assert not estado["padrão"]["enabled"] and not estado["empresa"]["enabled"]
    assert _hooks(outra / "settings.json")
    assert not (empresa / "settings.json").exists()


def test_desligar_um_perfil_nao_mexe_nos_outros(casa: Path) -> None:
    _perfil(casa, "empresa")
    runner.invoke(app, ["claude", "on"])
    r = runner.invoke(app, ["claude", "off", "--profile", "claude-code:empresa", "--json"])
    assert r.exit_code == 0, r.output
    estado = {p["name"]: p["enabled"] for p in json.loads(r.output)["profiles"]}
    assert estado == {"padrão": True, "empresa": False}


def test_perfil_desconhecido_e_recusado(casa: Path) -> None:
    r = runner.invoke(app, ["claude", "on", "--profile", "nao-existe"])
    assert r.exit_code == 2
    assert "não encontrado" in r.output


def test_adicionar_repetido_padrao_ou_pasta_inexistente(casa: Path, tmp_path: Path) -> None:
    empresa = _perfil(casa, "empresa")
    repetido = json.loads(runner.invoke(app, ["claude", "profiles", "add", str(empresa), "--json"]).output)
    assert repetido["ok"] is True and repetido["changed"] is False

    padrao = runner.invoke(app, ["claude", "profiles", "add", str(casa / ".claude"), "--json"])
    assert padrao.exit_code == 1 and "padrão" in json.loads(padrao.output)["error"]

    sumida = runner.invoke(app, ["claude", "profiles", "add", str(tmp_path / "nada"), "--json"])
    assert sumida.exit_code == 1


def test_tirar_da_lista_nao_mexe_na_configuracao(casa: Path, tmp_path: Path) -> None:
    outra = tmp_path / "cliente"
    outra.mkdir()
    runner.invoke(app, ["claude", "profiles", "add", str(outra), "--on"])
    assert is_registered(next(c for c in CLIENTS() if c.id == "claude-code:cliente"))

    r = runner.invoke(app, ["claude", "profiles", "remove", str(outra), "--json"])
    assert json.loads(r.output)["changed"] is True
    assert "claude-code:cliente" not in _ids()
    # a configuração que já estava lá continua: tirar da lista não é desligar
    assert "ragx" in json.loads((outra / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]


def test_duas_pastas_com_o_mesmo_nome_nao_colidem(casa: Path, tmp_path: Path) -> None:
    for base in ("a", "b"):
        pasta = tmp_path / base / "cliente"
        pasta.mkdir(parents=True)
        runner.invoke(app, ["claude", "profiles", "add", str(pasta)])
    assert _ids() == ["claude-code", "claude-code:cliente", "claude-code:cliente-2"]


def test_arquivo_de_perfis_ilegivel_e_ignorado(casa: Path) -> None:
    (casa / ".ragx").mkdir(exist_ok=True)
    (casa / ".ragx" / "claude-profiles.json").write_text("{quebrado", encoding="utf-8")
    assert _ids() == ["claude-code"]


# ── o hook de toque (PostToolUse, RAGX-0141) ────────────────────────────
def _toques(settings: Path) -> list[dict]:
    dados = json.loads(settings.read_text(encoding="utf-8"))
    return list(dados.get("hooks", {}).get("PostToolUse", []))


def test_on_instala_o_hook_de_toque_async_e_off_tira(casa: Path) -> None:
    settings = casa / ".claude" / "settings.json"
    runner.invoke(app, ["claude", "on"])
    runner.invoke(app, ["claude", "on"])  # idempotente
    grupos = _toques(settings)
    assert len(grupos) == 1
    assert grupos[0]["matcher"] == "Edit|Write|MultiEdit"
    (hook,) = grupos[0]["hooks"]
    assert hook["command"].endswith("touch --stdin-json")
    assert hook["async"] is True and hook["timeout"] == 10

    runner.invoke(app, ["claude", "off"])
    assert "hooks" not in json.loads(settings.read_text(encoding="utf-8"))


def test_no_touch_nao_instala_e_remove_o_que_havia(casa: Path) -> None:
    settings = casa / ".claude" / "settings.json"
    runner.invoke(app, ["claude", "on", "--no-touch"])
    assert _toques(settings) == []
    runner.invoke(app, ["claude", "on"])
    assert len(_toques(settings)) == 1
    runner.invoke(app, ["claude", "on", "--no-touch"])
    assert _toques(settings) == []
    assert len(_hooks(settings)) == 1  # a dica continua


def test_hook_de_toque_preserva_os_posttooluse_da_pessoa(casa: Path) -> None:
    settings = casa / ".claude" / "settings.json"
    alheio = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo fmt"}]}
    settings.write_text(json.dumps({"hooks": {"PostToolUse": [alheio]}}), encoding="utf-8")
    runner.invoke(app, ["claude", "on"])
    assert alheio in _toques(settings) and len(_toques(settings)) == 2
    runner.invoke(app, ["claude", "off"])
    assert _toques(settings) == [alheio]


def test_estado_informa_touch(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    r = runner.invoke(app, ["claude", "status", "--json"])
    assert r.exit_code == 0, r.output
    estado = json.loads(r.output)
    assert all(p["touch"] is True for p in estado["profiles"])

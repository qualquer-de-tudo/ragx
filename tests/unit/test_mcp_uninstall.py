"""`ragx mcp uninstall`: retirar o RAGX sem tocar no resto da configuração."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.clients.registry import CLIENTS, Outcome, register, unregister, unregister_all

pytestmark = pytest.mark.unit
runner = CliRunner()


@pytest.fixture()
def casa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    return home


def _cliente(cid: str):
    return next(c for c in CLIENTS() if c.id == cid)


def _instalar(cid: str) -> Path:
    c = _cliente(cid)
    c.config.parent.mkdir(parents=True, exist_ok=True)
    for m in c.markers:
        m.mkdir(parents=True, exist_ok=True)
    return c.config


def test_json_remove_so_o_ragx_e_preserva_o_resto(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text(
        json.dumps(
            {
                "theme": "dark",
                "mcpServers": {
                    "github": {"command": "gh-mcp", "args": []},
                    "ragx": {"command": "ragx", "args": ["mcp", "serve"]},
                },
            }
        ),
        encoding="utf-8",
    )
    r = unregister(_cliente("cursor"))
    assert r.outcome is Outcome.REMOVED
    assert r.backup is not None and r.backup.is_file()
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["theme"] == "dark"
    assert dados["mcpServers"] == {"github": {"command": "gh-mcp", "args": []}}


def test_json_ausente_e_idempotente(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text('{"mcpServers": {"x": {}}}', encoding="utf-8")
    r = unregister(_cliente("cursor"))
    assert r.outcome is Outcome.UNCHANGED
    assert r.backup is None
    assert alvo.read_text(encoding="utf-8") == '{"mcpServers": {"x": {}}}'


def test_sem_arquivo_de_configuracao_e_unchanged(casa: Path) -> None:
    _instalar("cursor")
    assert unregister(_cliente("cursor")).outcome is Outcome.UNCHANGED


def test_cliente_nao_instalado_e_absent(casa: Path) -> None:
    r = unregister(_cliente("windsurf"))
    assert r.outcome is Outcome.ABSENT and r.ok


def test_json_ilegivel_fica_intocado(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text('{"mcpServers": {"ragx": ', encoding="utf-8")
    r = unregister(_cliente("cursor"))
    assert r.outcome is Outcome.FAILED
    assert alvo.read_text(encoding="utf-8") == '{"mcpServers": {"ragx": '


def test_dry_run_nao_grava_nem_faz_backup(casa: Path) -> None:
    alvo = _instalar("cursor")
    register(_cliente("cursor"))
    antes = alvo.read_text(encoding="utf-8")
    r = unregister(_cliente("cursor"), dry_run=True)
    assert r.outcome is Outcome.REMOVED
    assert r.backup is None
    assert alvo.read_text(encoding="utf-8") == antes
    assert not list(alvo.parent.glob("*.ragx-backup-*"))


def test_toml_remove_a_tabela_e_preserva_comentarios_e_vizinhas(casa: Path) -> None:
    alvo = _instalar("codex")
    alvo.write_text(
        "# minha configuração\n"
        'model = "o3"\n'
        "\n"
        "[mcp_servers.ragx]\n"
        'command = "ragx"\n'
        'args = ["mcp", "serve"]\n'
        "\n"
        "[mcp_servers.ragx.env]\n"
        'X = "1"\n'
        "\n"
        "# do github\n"
        "[mcp_servers.github]\n"
        'command = "gh-mcp"\n'
        "args = []\n",
        encoding="utf-8",
    )
    r = unregister(_cliente("codex"))
    assert r.outcome is Outcome.REMOVED
    texto = alvo.read_text(encoding="utf-8")
    assert "# minha configuração" in texto and "# do github" in texto
    dados = tomllib.loads(texto)
    assert dados["model"] == "o3"
    assert "ragx" not in dados["mcp_servers"]
    assert dados["mcp_servers"]["github"]["command"] == "gh-mcp"


def test_toml_ausente_e_unchanged(casa: Path) -> None:
    alvo = _instalar("codex")
    original = 'model = "o3"\n'
    alvo.write_text(original, encoding="utf-8")
    assert unregister(_cliente("codex")).outcome is Outcome.UNCHANGED
    assert alvo.read_text(encoding="utf-8") == original


def test_toml_ilegivel_fica_intocado(casa: Path) -> None:
    alvo = _instalar("codex")
    quebrado = "[mcp_servers.ragx\ncommand = "
    alvo.write_text(quebrado, encoding="utf-8")
    assert unregister(_cliente("codex")).outcome is Outcome.FAILED
    assert alvo.read_text(encoding="utf-8") == quebrado


def test_unregister_all_respeita_only(casa: Path) -> None:
    _instalar("cursor")
    _instalar("gemini")
    register(_cliente("cursor"))
    register(_cliente("gemini"))
    rs = unregister_all(only=["cursor"])
    assert [r.client.id for r in rs] == ["cursor"]
    assert rs[0].outcome is Outcome.REMOVED
    assert "ragx" in json.loads(_cliente("gemini").config.read_text("utf-8"))["mcpServers"]


def test_cli_uninstall_json(casa: Path) -> None:
    _instalar("cursor")
    register(_cliente("cursor"))
    r = runner.invoke(app, ["mcp", "uninstall", "--client", "cursor", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados[0]["client"] == "cursor" and dados[0]["outcome"] == "removed"
    assert "ragx" not in json.loads(_cliente("cursor").config.read_text("utf-8"))["mcpServers"]


def test_cli_uninstall_texto_e_dry_run(casa: Path) -> None:
    _instalar("cursor")
    register(_cliente("cursor"))
    antes = _cliente("cursor").config.read_text("utf-8")
    r = runner.invoke(app, ["mcp", "uninstall", "--client", "cursor", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "simulação" in r.output
    assert _cliente("cursor").config.read_text("utf-8") == antes


def test_cli_uninstall_falha_devolve_codigo_1(casa: Path) -> None:
    _instalar("cursor").write_text("{quebrado", encoding="utf-8")
    r = runner.invoke(app, ["mcp", "uninstall", "--client", "cursor"])
    assert r.exit_code == 1

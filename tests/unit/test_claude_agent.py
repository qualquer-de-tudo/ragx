"""O subagente `ragx-explorer` (RAGX-0161). HOME redirecionado: nunca o `~/.claude` real."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.clients import claude_agent
from ragx.config import load_config
from ragx.mcp.server import build_server
from ragx.tokens import count_tokens

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
    (pasta / ".claude.json").write_text("{}", encoding="utf-8")
    return pasta


def _arquivo(home: Path) -> Path:
    return home / ".claude" / "agents" / "ragx-explorer.md"


def _frontmatter(texto: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", texto, re.S)
    assert m, "sem frontmatter"
    dados = yaml.safe_load(m.group(1))
    assert isinstance(dados, dict)
    return dados


# ── o conteúdo ──────────────────────────────────────────────────────────
def test_frontmatter_e_yaml_valido_e_so_leitura() -> None:
    fm = _frontmatter(claude_agent.agent_text())
    assert fm["name"] == "ragx-explorer" and fm["description"] == claude_agent.DESCRIPTION
    ferramentas = [t.strip() for t in fm["tools"].split(",")]
    assert ferramentas == list(claude_agent.TOOLS)
    assert not {"Edit", "Write", "Bash", "MultiEdit", "NotebookEdit"} & set(ferramentas)
    assert "model" not in fm  # herda; a pessoa fixa, se quiser
    texto = claude_agent.agent_text()
    assert texto.split("\n---\n", 1)[1].lstrip().startswith(claude_agent.MARKER)  # logo após o frontmatter


def test_a_description_cabe_em_60_tokens() -> None:
    assert count_tokens(claude_agent.DESCRIPTION) <= 60


@pytest.mark.parametrize("perfil", ["full", "slim"])
def test_toda_ferramenta_mcp_ragx_do_agente_existe_nos_dois_perfis(tmp_path: Path, perfil: str) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    expostas = {t.name for t in asyncio.run(build_server(load_config(tmp_path), profile=perfil).list_tools())}
    nomes = {t.removeprefix("mcp__ragx__") for t in claude_agent.TOOLS if t.startswith("mcp__ragx__")}
    assert nomes and nomes <= expostas, (perfil, nomes - expostas)


# ── instalar, idempotência, dry-run, arquivo alheio ─────────────────────
def test_install_cria_o_arquivo_e_rodar_de_novo_nao_muda_nada(casa: Path) -> None:
    r = runner.invoke(app, ["claude", "agent", "install"])
    assert r.exit_code == 0, r.output
    arquivo = _arquivo(casa)
    assert arquivo.read_text(encoding="utf-8") == claude_agent.agent_text()
    antes = arquivo.stat().st_mtime_ns
    runner.invoke(app, ["claude", "agent", "install"])
    assert arquivo.stat().st_mtime_ns == antes and list(arquivo.parent.glob("*.ragx-backup-*")) == []


def test_dry_run_nao_escreve(casa: Path) -> None:
    r = runner.invoke(app, ["claude", "agent", "install", "--dry-run"])
    assert r.exit_code == 0 and not _arquivo(casa).exists() and not _arquivo(casa).parent.exists()


def test_arquivo_da_pessoa_com_o_mesmo_nome_nao_e_sobrescrito(casa: Path) -> None:
    alheio = _arquivo(casa)
    alheio.parent.mkdir(parents=True)
    alheio.write_text("---\nname: ragx-explorer\ndescription: meu\n---\nmeu texto\n", encoding="utf-8")
    r = runner.invoke(app, ["claude", "agent", "install"])
    assert r.exit_code == 1 and "não é do RAGX" in r.output
    assert alheio.read_text(encoding="utf-8").endswith("meu texto\n")
    runner.invoke(app, ["claude", "agent", "remove"])  # e o remove também o deixa
    assert alheio.exists()


def test_versao_antiga_com_o_marcador_e_atualizada_com_backup(casa: Path) -> None:
    arquivo = _arquivo(casa)
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text(f"---\nname: ragx-explorer\ndescription: velha\n---\n{claude_agent.MARKER}\nvelho\n", encoding="utf-8")
    r = runner.invoke(app, ["claude", "agent", "install"])
    assert r.exit_code == 0
    assert arquivo.read_text(encoding="utf-8") == claude_agent.agent_text()
    assert len(list(arquivo.parent.glob("*.ragx-backup-*"))) == 1


def test_remove_apaga_so_o_arquivo_com_o_marcador(casa: Path) -> None:
    runner.invoke(app, ["claude", "agent", "install"])
    assert _arquivo(casa).exists()
    runner.invoke(app, ["claude", "agent", "remove"])
    assert not _arquivo(casa).exists()
    r = runner.invoke(app, ["claude", "agent", "remove"])  # já não existe: não é erro
    assert r.exit_code == 0


# ── vários perfis, `on`/`off`, status ───────────────────────────────────
def test_vai_para_cada_perfil_ou_so_para_o_pedido(casa: Path) -> None:
    empresa = _perfil(casa, "empresa")
    runner.invoke(app, ["claude", "agent", "install", "--profile", "empresa"])
    assert (empresa / "agents" / "ragx-explorer.md").is_file() and not _arquivo(casa).exists()
    runner.invoke(app, ["claude", "agent", "install"])
    assert _arquivo(casa).is_file()


def test_on_nao_instala_o_agente_por_padrao_e_com_agent_instala(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    assert not _arquivo(casa).exists()  # um subagente novo na lista da pessoa é opt-in
    runner.invoke(app, ["claude", "on", "--agent"])
    assert _arquivo(casa).is_file()


def test_off_remove_o_agente_nosso_e_preserva_o_alheio(casa: Path) -> None:
    runner.invoke(app, ["claude", "on", "--agent"])
    runner.invoke(app, ["claude", "off"])
    assert not _arquivo(casa).exists()
    alheio = _arquivo(casa)
    alheio.parent.mkdir(parents=True, exist_ok=True)
    alheio.write_text("---\nname: ragx-explorer\ndescription: meu\n---\n", encoding="utf-8")
    runner.invoke(app, ["claude", "off"])
    assert alheio.exists()


def test_status_json_traz_agent_por_perfil(casa: Path) -> None:
    antes = json.loads(runner.invoke(app, ["claude", "status", "--json"]).output)
    assert all(p["agent"] is False for p in antes["profiles"])
    runner.invoke(app, ["claude", "agent", "install"])
    depois = json.loads(runner.invoke(app, ["claude", "status", "--json"]).output)
    assert all(p["agent"] is True and "hint" in p and "touch" in p and "nudge" in p for p in depois["profiles"])
    st = json.loads(runner.invoke(app, ["claude", "agent", "status", "--json"]).output)
    assert st["agents"][0]["installed"] is True and st["agents"][0]["path"].endswith("ragx-explorer.md")

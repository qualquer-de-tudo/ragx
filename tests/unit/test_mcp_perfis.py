"""Perfis do servidor MCP: `full` (33 ferramentas) e `slim` (6) — RAGX-0157."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.config import McpCfg, load_config
from ragx.mcp.server import SLIM_TOOLS, build_server
from ragx.perf import footprint_tokens

pytestmark = pytest.mark.unit
runner = CliRunner()

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


@pytest.fixture()
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _listar(cfg, **kw):  # type: ignore[no-untyped-def]
    return asyncio.run(build_server(cfg, allow_write=True, **kw).list_tools())


def test_o_padrao_e_slim_e_o_full_continua_disponivel(projeto: Path) -> None:
    """Desde a v1.0.0 o padrão é `slim` (decisão da pessoa, RAGX-0157); o `full` é pedido por nome."""
    assert McpCfg().profile == "slim"
    assert len(_listar(load_config(projeto))) == 6
    assert len(_listar(load_config(projeto), profile="full")) == 33


def test_slim_expoe_so_as_seis_com_os_mesmos_nomes(projeto: Path) -> None:
    nomes = {t.name for t in _listar(load_config(projeto), profile="slim")}
    assert nomes == set(SLIM_TOOLS) == {
        "get_dictionary", "search_hybrid", "build_context", "get_chunk", "get_entity", "refresh",
    }
    # todos existem no full, com o mesmo nome
    assert nomes <= {t.name for t in _listar(load_config(projeto))}


def test_o_perfil_chega_pelo_ambiente_e_pelo_toml(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAGX_MCP_PROFILE", "slim")
    assert load_config(projeto).mcp.profile == "slim"
    assert len(_listar(load_config(projeto))) == 6
    monkeypatch.delenv("RAGX_MCP_PROFILE")
    (projeto / "ragx.toml").write_text(TOML + '\n[mcp]\nprofile = "slim"\n', encoding="utf-8")
    assert load_config(projeto).mcp.profile == "slim"


def test_schemas_do_slim_sem_title_anyof_nem_default(projeto: Path) -> None:
    for t in _listar(load_config(projeto), profile="slim"):
        texto = json.dumps(t.input_schema)
        assert '"title"' not in texto, t.name
        assert '"anyOf"' not in texto, t.name
        assert '"default"' not in texto, t.name
    # e continuam descrevendo os argumentos
    busca = next(t for t in _listar(load_config(projeto), profile="slim") if t.name == "search_hybrid")
    assert {"query", "limit", "scope"} <= set(busca.input_schema["properties"])
    assert busca.input_schema["required"] == ["query"]


def test_o_custo_fixo_do_slim_cabe_em_600_tokens(projeto: Path) -> None:
    n, tokens = footprint_tokens(_listar(load_config(projeto), profile="slim"))
    assert n == 6 and tokens <= 600, tokens
    n_full, tokens_full = footprint_tokens(_listar(load_config(projeto), profile="full"))
    assert n_full == 33 and tokens_full > 4 * tokens  # o slim é MUITO menor


def test_a_regua_le_input_schema(projeto: Path) -> None:
    """Lia `inputSchema` (SDK 1.x): no 2.x o campo é `input_schema` e o custo saía ~60% menor."""

    esquema = {"type": "object", "properties": {f"p{i}": {"type": "string"} for i in range(40)}}
    fake = SimpleNamespace(name="x", description="d", input_schema=esquema)

    n, tokens = footprint_tokens([fake])
    assert n == 1 and tokens > 100


def test_mcp_tools_json_traz_o_schema_nao_nulo(projeto: Path) -> None:
    r = runner.invoke(app, ["mcp", "tools", "--json", "--profile", "slim"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert len(dados) == 6 and all(d["input_schema"] for d in dados)


def test_perfil_desconhecido_e_recusado(projeto: Path) -> None:
    r = runner.invoke(app, ["mcp", "tools", "--profile", "enorme"])
    assert r.exit_code != 0


def test_as_instrucoes_do_slim_so_citam_ferramentas_que_ele_expoe(projeto: Path) -> None:
    server = build_server(load_config(projeto), allow_write=True, profile="slim")
    instrucoes = server.instructions
    assert "get_dictionary" in instrucoes and "refresh" in instrucoes
    for ausente in ("get_playbook", "sync", "reindex", "search_graph", "task_status"):
        assert ausente not in re.findall(r"[a-z_]+", instrucoes), ausente  # a palavra, não "reindexar"


# ── as seis respondem no slim ───────────────────────────────────────────
def _chamar(cfg, nome: str, write: bool = False, **args):  # type: ignore[no-untyped-def]
    server = build_server(cfg, allow_write=write, profile="slim")
    r = asyncio.run(server.call_tool(nome, args))
    dados = json.loads("".join(b.text for b in r.content))
    return dados.get("data", dados), dados


def test_as_seis_respondem_corretamente_no_slim(projeto: Path) -> None:
    from ragx.dictionary import builder
    from ragx.graph.service import rebuild
    from ragx.indexing.pipeline import index_project

    (projeto / "auth.py").write_text(
        'class AuthService:\n    """Autentica usuarios."""\n\n    def login(self, token):\n        return token\n',
        encoding="utf-8",
    )
    cfg = load_config(projeto)
    index_project(cfg)
    rebuild(cfg)
    data, _ = builder.build(cfg)
    builder.write(cfg, data)

    assert "dictionary" in _chamar(cfg, "get_dictionary")[0]
    achados = _chamar(cfg, "search_hybrid", query="autentica usuarios", response_format="detailed")[0]["results"]
    assert achados
    contexto = _chamar(cfg, "build_context", query="login", tokens=500)[0]
    assert "markdown" in contexto
    assert _chamar(cfg, "get_chunk", chunk_id=achados[0]["chunk_id"])[0]
    assert _chamar(cfg, "get_entity", name="AuthService")[0]["entity"]["name"] == "AuthService"
    assert _chamar(cfg, "refresh", write=True)[1]["ok"] is True


def test_refresh_em_modo_leitura_responde_write_disabled(projeto: Path) -> None:
    from ragx.indexing.pipeline import index_project

    (projeto / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_project(load_config(projeto))
    _, bruto = _chamar(load_config(projeto), "refresh", write=False)
    assert bruto["ok"] is False and bruto["error"]["code"] == "write_disabled"

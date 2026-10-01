from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.mcp.server import build_server

pytestmark = pytest.mark.integration


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text(
        'class AuthService:\n    """Login via SSO."""\n    def login(self):\n        pass\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    return tmp_path


def _log_lines(proj: Path) -> list[dict]:
    log_path = proj / ".ragx" / "logs" / "mcp.jsonl"
    if not log_path.is_file():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _call_tool(cfg, name: str, **kwargs):
    server = build_server(cfg, allow_write=False)
    tools = {t.name: t for t in await server.list_tools()}
    assert name in tools
    return await server.call_tool(name, kwargs)


def test_successful_call_logs_tool_and_ms(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "get_dictionary"))

    lines = _log_lines(proj)
    assert len(lines) == 1
    assert lines[0]["tool"] == "get_dictionary"
    assert isinstance(lines[0]["ms"], (int, float))
    assert lines[0]["ms"] >= 0
    assert "project" in lines[0]
    assert "tokens_delivered" not in lines[0]
    # RAGX-0156: o registro diz se deu certo e quanto saiu no fio
    assert lines[0]["v"] == 2
    assert lines[0]["ok"] is True
    assert lines[0]["resp_chars"] > 0 and lines[0]["resp_tokens"] > 0
    assert len(lines[0]["proc"]) == 8
    assert "err_code" not in lines[0]


def test_build_context_logs_tokens_delivered(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "build_context", query="login sso", tokens=500))

    lines = _log_lines(proj)
    matching = [entry for entry in lines if entry["tool"] == "build_context"]
    assert len(matching) == 1
    assert isinstance(matching[0]["tokens_delivered"], int)


def test_build_context_logs_baseline_from_index(proj: Path) -> None:
    """O "sem RAGX" do gráfico: tamanho dos arquivos-fonte inteiros, lido do índice."""
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "build_context", query="login sso", tokens=500))

    entry = next(e for e in _log_lines(proj) if e["tool"] == "build_context")

    from ragx.mcp.server import KnowledgeAPI
    from ragx.mcp.tools import BuildContextRequest

    fontes = KnowledgeAPI(cfg).build_context(BuildContextRequest(query="login sso", tokens=500))["data"]["sources"]
    assert "auth.py" in fontes
    # Na MESMA unidade do que é entregue (tokens do contador, `chunks.token_count`), e não
    # `size_bytes // 4`, que em markdown erra por ~30% (RAGX-0163)
    import sqlite3

    conn = sqlite3.connect(cfg.db_path)
    marcas = ",".join("?" * len(fontes))
    esperado = conn.execute(
        "SELECT COALESCE(SUM(c.token_count), 0) FROM chunks c JOIN documents d "
        f"ON d.id = c.document_id WHERE d.rel_path IN ({marcas})",
        list(fontes),
    ).fetchone()[0]
    conn.close()
    assert entry["baseline_tokens"] == esperado


def test_failed_call_still_logs(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    # get_chunk com id inexistente -> falha tratada (ok: false), nao excecao crua
    asyncio.run(_call_tool(cfg, "get_chunk", chunk_id="nao-existe"))

    lines = _log_lines(proj)
    assert len(lines) == 1
    assert lines[0]["tool"] == "get_chunk"
    # antes: gravada como sucesso, sem `ok`; a taxa de erro não era calculável
    assert lines[0]["ok"] is False
    assert lines[0]["err_code"] == "invalid_id"


def test_validation_error_still_logs(proj: Path) -> None:
    """`query=""` viola `min_length=1` de `SearchRequest.query` -> ValidationError
    -> `invalid_argument`. Mesmo assim deve gerar uma linha de telemetria: a
    reclamacao original de que 'toda chamada gera uma linha' nao se sustentava
    quando so o caminho de sucesso logava."""
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "search_hybrid", query=""))

    lines = _log_lines(proj)
    assert len(lines) == 1
    assert lines[0]["tool"] == "search_hybrid"
    assert lines[0]["ok"] is False
    assert lines[0]["err_code"] == "invalid_argument"


def test_chamada_sem_indice_nao_cria_pasta_ragx(tmp_path: Path) -> None:
    """Uma pasta que nao e um projeto RAGX (sem ragx.toml, sem indice) nao pode
    ganhar um `.ragx/` so por causa de uma chamada MCP bem-sucedida como
    `get_playbook`, que nao precisa de indice."""
    import asyncio

    cfg = load_config(tmp_path)
    assert not cfg.db_path.exists()

    asyncio.run(_call_tool(cfg, "get_playbook"))

    assert not (tmp_path / ".ragx").exists(), "chamada MCP sem indice nao deve criar .ragx/"


def test_resp_chars_e_o_tamanho_exato_do_texto_devolvido(proj: Path) -> None:
    """O registro usa o texto que o cliente recebe, não uma estimativa do dict."""
    import asyncio

    cfg = load_config(proj)
    casos = [
        ("get_dictionary", {}),
        ("get_chunk", {"chunk_id": "0" * 12}),         # not_found
        ("search_hybrid", {"query": ""}),              # invalid_argument
        ("build_context", {"query": "login sso", "tokens": 500}),
    ]
    for nome, args in casos:
        resp = asyncio.run(_call_tool(cfg, nome, **args))
        texto = "".join(b.text for b in resp.content)
        entrada = [e for e in _log_lines(proj) if e["tool"] == nome][-1]
        assert entrada["resp_chars"] == len(texto), nome


def test_chamada_limitada_pelo_rate_limit_grava_rate_limited(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    cfg.mcp.rate_per_min = 1
    server = build_server(cfg, allow_write=False)
    asyncio.run(server.call_tool("get_dictionary", {}))
    asyncio.run(server.call_tool("get_dictionary", {}))
    ultimas = [e for e in _log_lines(proj) if e["tool"] == "get_dictionary"]
    assert ultimas[-1]["ok"] is False and ultimas[-1]["err_code"] == "rate_limited"


def test_a_linha_nunca_traz_a_consulta_nem_a_mensagem_de_erro(proj: Path) -> None:
    import asyncio

    cfg = load_config(proj)
    asyncio.run(_call_tool(cfg, "search_hybrid", query="login sso"))
    asyncio.run(_call_tool(cfg, "get_chunk", chunk_id="nao-existe-segredo"))
    bruto = (proj / ".ragx" / "logs" / "mcp.jsonl").read_text(encoding="utf-8")
    assert "login sso" not in bruto and "nao-existe-segredo" not in bruto

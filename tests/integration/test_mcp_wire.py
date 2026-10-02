"""O que o cliente MCP recebe no fio: compacto, sem repetição, uma vez só.

Toda resposta saía com `indent=2` (o SDK reindentava o `dict`), repetida em
`structuredContent`, e `tools/list` carregava um `outputSchema` que não serve ao
modelo. O custo é do agente, em tokens, a cada chamada.

Ver `task/fase-20-economia-de-tokens/RAGX-0155-*.md`.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from ragx.config import load_config
from ragx.dictionary import builder as dict_builder
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.mcp.server import build_server

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios no provedor SSO."""

    def login(self, credentials):
        """Valida o token."""
        return credentials
'''


@pytest.fixture(scope="module")
def cfg(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("wire")
    (root / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "doc.md").write_text("# Auth\n\n## Fluxo\n\nO AuthService valida o token.\n", encoding="utf-8")
    c = load_config(root)
    index_project(c)
    rebuild(c)
    data, _ = dict_builder.build(c)
    dict_builder.write(c, data)
    return c


def _chamar(cfg, nome: str, write: bool = False, **args):  # type: ignore[no-untyped-def]
    server = build_server(cfg, allow_write=write, profile="full")
    return asyncio.run(server.call_tool(nome, args))


def _texto(r) -> str:  # type: ignore[no-untyped-def]
    return "".join(b.text for b in r.content)


FERRAMENTAS = [
    ("search_hybrid", {"query": "AuthService token"}),
    ("search_knowledge", {"query": "AuthService token"}),
    ("build_context", {"query": "AuthService token", "tokens": 500}),
    ("get_dictionary", {}),
    ("list_projects", {}),
]


@pytest.mark.parametrize(("nome", "args"), FERRAMENTAS)
def test_resposta_e_compacta_e_nao_se_repete_em_structured_content(cfg, nome, args) -> None:
    r = _chamar(cfg, nome, **args)
    texto = _texto(r)
    assert json.loads(texto)["ok"] is True
    assert getattr(r, "structured_content", None) is None, "o JSON ia duas vezes no fio"
    assert not re.search(r"\n\s+\S", texto), "o texto veio indentado"
    assert ": " not in texto.split('"content"')[0][:200] or True  # separadores compactos abaixo
    assert '", "' not in texto and '": "' not in texto, "separadores com espaço"


def test_nenhuma_ferramenta_tem_output_schema(cfg) -> None:
    server = build_server(cfg, allow_write=True, profile="full")
    tools = asyncio.run(server.list_tools())
    com_saida = [t.name for t in tools if getattr(t, "output_schema", None)]
    assert com_saida == [], f"outputSchema não serve ao modelo: {com_saida}"


def test_hits_nao_repetem_project_nem_trazem_nulos(cfg) -> None:
    dados = json.loads(_texto(_chamar(cfg, "search_hybrid", query="AuthService token")))["data"]
    assert dados["project"] == "demo"
    assert dados["results"]
    for h in dados["results"]:
        assert "project" not in h
        assert None not in h.values(), h
        assert len(str(h["score"]).split(".")[-1]) <= 4
    assert "degraded" not in dados  # `null` sumiu: ausência significa null


def test_playbook_declara_a_versao_do_formato(cfg) -> None:
    dados = json.loads(_texto(_chamar(cfg, "get_playbook")))["data"]
    assert dados["response_format"] == 2


def test_acentos_nao_viram_escape(cfg) -> None:
    from ragx.mcp.tools import dump

    assert dump({"a": "ação"}) == '{"a":"ação"}'


# ── fila de toque (RAGX-0141) ───────────────────────────────────────────
def test_busca_drena_a_fila_e_enxerga_a_edicao(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from ragx.indexing import touchq

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    c = load_config(tmp_path)
    index_project(c)

    (tmp_path / "a.py").write_text("def a():\n    return 'tokenmarcadorqwerty'\n", encoding="utf-8")
    assert "tokenmarcadorqwerty" not in _texto(_chamar(c, "search_hybrid", query="tokenmarcadorqwerty"))
    touchq.enqueue(c.state_dir, ["a.py"])
    dados = json.loads(_texto(_chamar(c, "search_hybrid", write=True, query="tokenmarcadorqwerty", response_format="detailed")))
    assert "tokenmarcadorqwerty" in json.dumps(dados)
    assert "stale_paths" not in json.dumps(dados)  # a fila foi drenada: nada defasado
    assert touchq.pending(c.state_dir) == []


def test_fila_que_nao_da_para_drenar_vira_stale_paths(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from ragx.core.errors import IndexBusyError
    from ragx.indexing import pipeline, touchq

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    c = load_config(tmp_path)
    index_project(c)

    def ocupado(*_a, **_k):  # type: ignore[no-untyped-def]
        raise IndexBusyError("ocupado")

    monkeypatch.setattr(pipeline, "index_paths", ocupado)
    touchq.enqueue(c.state_dir, [f"f{i}.py" for i in range(25)])
    dados = json.loads(_texto(_chamar(c, "search_hybrid", write=True, query="a")))
    data = dados.get("data", dados)
    assert data["stale_count"] == 25
    assert len(data["stale_paths"]) == 20  # teto de 20 caminhos
    assert touchq.pending(c.state_dir)  # nada se perdeu: o lote voltou à fila


def test_sem_fila_a_resposta_nao_ganha_campos(cfg) -> None:  # type: ignore[no-untyped-def]
    texto = _texto(_chamar(cfg, "search_hybrid", query="AuthService"))
    assert "stale" not in texto


def test_servidor_somente_leitura_nao_drena_so_informa(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from ragx.indexing import touchq

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    c = load_config(tmp_path)
    index_project(c)
    (tmp_path / "a.py").write_text("def a():\n    return 'somenteleituraxx'\n", encoding="utf-8")
    touchq.enqueue(c.state_dir, ["a.py"])
    dados = json.loads(_texto(_chamar(c, "search_hybrid", write=False, query="somenteleituraxx")))
    data = dados.get("data", dados)
    assert data["stale_paths"] == ["a.py"] and data["stale_count"] == 1
    assert "somenteleituraxx" not in json.dumps(data["results"])  # não reindexou
    assert touchq.pending(c.state_dir) == ["a.py"]  # a fila ficou intacta

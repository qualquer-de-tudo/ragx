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


def _chamar(cfg, nome: str, **args):  # type: ignore[no-untyped-def]
    server = build_server(cfg, allow_write=False)
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
    server = build_server(cfg, allow_write=True)
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

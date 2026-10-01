"""A lista de ferramentas e as `instructions` do MCP são estáveis, curtas e legíveis (RAGX-0158).

O Claude Code trunca as `instructions` em ~2 KB, descobre ferramentas por Tool Search (que lê nome e
descrição) e perde o cache de prompt quando a lista muda. Por isso: teto de bytes, descrição curta com
verbo no início, e um arquivo-ouro que obriga a regravar DE PROPÓSITO quando uma descrição ou um schema
muda.

    RAGX_REGRAVAR_OURO=1 uv run pytest tests/integration/test_mcp_estavel.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.mcp.playbook import INSTRUCTIONS_MAX_BYTES, short_instructions
from ragx.mcp.server import SLIM_TOOLS, build_server

pytestmark = pytest.mark.integration

OURO = Path(__file__).resolve().parents[1] / "fixtures"
TOML = '[project]\nname = "t"\nid = "t"\n'

#: Verbos com que uma descrição pode começar. Ferramenta nova com outro verbo: acrescente-o aqui
#: de propósito (o ponto é a descrição dizer o que a ferramenta FAZ, no começo, para o Tool Search).
VERBOS = {
    "Ensina", "Mostra", "Busca", "Localiza", "Lista", "Abre", "Monta", "Reindexa", "Sincroniza",
    "Reconstrói", "Regenera", "Instala", "Republica", "Classifica", "Indica", "Reivindica",
    "Entrega", "Devolve", "Muda", "Cria", "Roda",
}


@pytest.fixture(scope="module")
def cfg(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    raiz = tmp_path_factory.mktemp("estavel")
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    return load_config(raiz)


def _listar(cfg, perfil: str, escrita: bool = True):  # type: ignore[no-untyped-def]
    return asyncio.run(build_server(cfg, allow_write=escrita, profile=perfil).list_tools())


def _serializar(listadas) -> str:  # type: ignore[no-untyped-def]
    return json.dumps(
        [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in listadas],
        ensure_ascii=False, indent=1, sort_keys=True,
    ) + "\n"


@pytest.mark.parametrize("perfil", ["full", "slim"])
@pytest.mark.parametrize("escrita", [True, False])
def test_instructions_cabem_em_2kb_e_so_citam_ferramentas_do_perfil(perfil: str, escrita: bool) -> None:
    texto = short_instructions(escrita, perfil)
    assert len(texto.encode("utf-8")) <= INSTRUCTIONS_MAX_BYTES
    if perfil == "slim":  # as do `full` são conferidas contra a lista real no teste seguinte
        citadas = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b|\brefresh\b|\bsync\b", texto))
        for nome in citadas:
            assert nome in SLIM_TOOLS, f"as instructions do slim citam {nome}, que o perfil não expõe"
        assert "get_playbook" not in texto


def test_as_instructions_do_full_so_citam_ferramentas_que_existem(cfg) -> None:  # type: ignore[no-untyped-def]
    existentes = {t.name for t in _listar(cfg, "full")}
    texto = short_instructions(True, "full")
    for nome in re.findall(r"\b[a-z]+(?:_[a-z]+)+\b|\brefresh\b|\bsync\b", texto):
        assert nome in existentes, nome


def test_as_instructions_nao_dependem_de_estado_da_sessao(cfg) -> None:  # type: ignore[no-untyped-def]
    a = build_server(cfg, allow_write=True, profile="full").instructions
    b = build_server(cfg, allow_write=True, profile="full").instructions
    assert a == b == short_instructions(True, "full")
    assert not re.search(r"\d{4}-\d{2}-\d{2}", a)  # nenhuma data


@pytest.mark.parametrize("perfil", ["full", "slim"])
def test_toda_descricao_tem_ate_200_caracteres_e_comeca_por_verbo(cfg, perfil: str) -> None:  # type: ignore[no-untyped-def]
    for t in _listar(cfg, perfil):
        assert len(t.description) <= 200, f"{t.name}: {len(t.description)} caracteres"
        primeira = t.description.split()[0]
        assert primeira in VERBOS, f"{t.name} começa por {primeira!r}, que não é um verbo da lista"
        assert not re.search(r"\d{4}-\d{2}-\d{2}|\b\d+ (projetos|chunks|documentos)\b", t.description), t.name


def test_a_descricao_do_localizar_usa_os_termos_de_quem_procura(cfg) -> None:  # type: ignore[no-untyped-def]
    d = {t.name: t.description.lower() for t in _listar(cfg, "full")}
    assert "localiza" in d["search_hybrid"] and "onde" in d["search_hybrid"]
    assert "quem" in d["get_entity"] and "chama" in d["get_entity"]
    assert "reindexa" in d["refresh"] and "reindexa" in d["reindex"]


@pytest.mark.parametrize("perfil", ["full", "slim"])
def test_list_tools_e_identico_em_duas_chamadas_e_ao_arquivo_ouro(cfg, perfil: str) -> None:  # type: ignore[no-untyped-def]
    primeira = _serializar(_listar(cfg, perfil))
    assert primeira == _serializar(_listar(cfg, perfil))
    # a escrita ligada ou não NÃO muda a lista (as ferramentas de escrita existem e respondem `write_disabled`)
    assert primeira == _serializar(_listar(cfg, perfil, escrita=False))

    arquivo = OURO / f"mcp_tools_{perfil}.json"
    if os.environ.get("RAGX_REGRAVAR_OURO") == "1":
        arquivo.write_text(primeira, encoding="utf-8", newline="\n")
    assert arquivo.is_file(), f"falta {arquivo}; gere com RAGX_REGRAVAR_OURO=1"
    assert primeira == arquivo.read_text(encoding="utf-8"), (
        f"a lista de ferramentas do perfil {perfil} mudou. Se a mudança é intencional, regrave o arquivo-ouro:\n"
        "  RAGX_REGRAVAR_OURO=1 uv run pytest tests/integration/test_mcp_estavel.py\n"
        "e revise o diff: nome, descrição ou schema que mudam invalidam o cache de prompt do cliente."
    )

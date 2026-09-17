"""A documentação do MCP acompanha as ferramentas — verificado, não prometido.

`docs/09-mcp.md` chegou a documentar 20 das 33 ferramentas: as 13 de
orquestração de tarefas existiam, funcionavam e não estavam escritas em lugar
nenhum. Ninguém percebeu porque nada quebra quando a documentação encolhe.

Este teste é o que faz encolher doer. Ele compara a lista REGISTRADA no
servidor com a lista CITADA no documento, nos dois sentidos:

- ferramenta sem documentação: o agente não descobre que ela existe;
- documentação sem ferramenta: o agente tenta chamar e recebe erro.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOC = RAIZ / "docs" / "09-mcp.md"

#: Ferramenta citada como `` `nome` `` numa tabela do documento.
_CITADA = re.compile(r"^\|\s*`([a-z_][a-z0-9_]*)`\s*\|", re.M)


def _registradas() -> set[str]:
    """Os nomes que o servidor realmente expõe.

    Vem de `build_server`, e não de uma lista escrita à mão: uma lista à mão
    é só mais um lugar para esquecer de atualizar.
    """
    from ragx.config import load_config
    from ragx.mcp.server import build_server

    server = build_server(load_config(), allow_write=True)
    return {t.name for t in asyncio.run(server.list_tools())}


def _secao_de_ferramentas(texto: str) -> str:
    """Só a seção "## Ferramentas".

    Fora dela há tabelas de LIMITES, cujas linhas começam com o nome de um
    parâmetro (`path_glob`, `limit`) na mesma forma de uma linha de ferramenta.
    Varrer o documento inteiro fazia o teste acusar `path_glob` de ser uma
    ferramenta que não existe.
    """
    inicio = texto.find("\n## Ferramentas")
    if inicio < 0:
        return texto
    fim = texto.find("\n## ", inicio + 1)
    return texto[inicio : fim if fim > 0 else len(texto)]


def _documentadas() -> set[str]:
    return set(_CITADA.findall(_secao_de_ferramentas(DOC.read_text(encoding="utf-8"))))


pytestmark = pytest.mark.skipif(not DOC.is_file(), reason="docs/09-mcp.md ausente")


def test_toda_ferramenta_registrada_esta_documentada() -> None:
    faltando = sorted(_registradas() - _documentadas())
    assert not faltando, (
        f"ferramentas MCP sem documentação em docs/09-mcp.md: {faltando}. "
        f"O agente descobre a ferramenta pelo documento antes de chamá-la."
    )


def test_o_documento_nao_promete_ferramenta_inexistente() -> None:
    sobrando = sorted(_documentadas() - _registradas())
    assert not sobrando, (
        f"docs/09-mcp.md cita ferramentas que o servidor não expõe: {sobrando}. "
        f"O agente tenta chamar e recebe 'unknown tool'."
    )


def test_o_readme_nao_promete_uma_contagem_que_o_codigo_desmente() -> None:
    """Se o README disser um número de ferramentas, que seja o número certo.

    A contagem no texto é frágil por natureza — este teste existe para que ela
    seja frágil de forma BARULHENTA, e não silenciosa.
    """
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    real = len(_registradas())
    for m in re.finditer(r"(\d+)\s+ferramentas", readme):
        assert int(m.group(1)) == real, (
            f"o README diz {m.group(1)} ferramentas MCP; o servidor expõe {real}."
        )

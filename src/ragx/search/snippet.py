"""Trecho curto de um chunk, para a busca `concise` do MCP (RAGX-0155/0165).

A busca serve para LOCALIZAR; o conteúdo inteiro de cada hit é o que mais pesa na
resposta (10 hits de ~600 chars cada). O trecho dá o suficiente para o agente decidir
se vale abrir (`get_chunk`) e custa uma fração. Lógica de serviço: o servidor MCP só a
chama, porque ele é casca fina (ADR-0006).
"""

from __future__ import annotations

_ELLIPSIS = "…"


def make_snippet(content: str, max_chars: int) -> str:
    """Os primeiros `max_chars` do conteúdo, cortados num fim de linha ou de palavra.

    Conteúdo que já cabe volta inteiro (sem reticências). Quando corta, termina em
    `…`. Prefere o último fim de linha se ele estiver nos últimos 40% da janela (um
    trecho de código termina numa linha inteira); senão, o último espaço; uma palavra
    única maior que a janela é cortada no limite.
    """
    texto = content.rstrip()
    if max_chars <= 0:
        return ""
    if len(texto) <= max_chars:
        return texto
    janela = texto[:max_chars]
    corte = janela.rfind("\n")
    if corte < int(max_chars * 0.6):
        corte = janela.rfind(" ")
    if corte <= 0:
        corte = max_chars
    return janela[:corte].rstrip() + _ELLIPSIS

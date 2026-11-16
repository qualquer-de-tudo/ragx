"""Mede quantos tokens uma busca do MCP devolve, no fio (RAGX-0203).

Chama `search_hybrid` pelo servidor MCP do projeto (perfil slim, o padrão) com um conjunto fixo de consultas e conta os
tokens do texto que o agente recebe, com o mesmo contador do restante dos benchmarks (tiktoken cl100k, que não é o
tokenizador do Claude). Meta: uma busca do RAGX não pode custar mais do que um grep (~400 tokens no uso real do
Juriflux); o teto do projeto é 600.

    uv run python scripts/medir_busca.py [--limit N] [--format concise|detailed]

Só lê o índice do diretório atual; não indexa nem escreve nada.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics

from ragx.config import load_config
from ragx.mcp.server import build_server
from ragx.tokens import count_tokens

CONSULTAS = [
    "onde o token é validado",
    "Security Gate antes do parser",
    "como o touch reindexa arquivos editados",
    "registro do servidor MCP no Codex",
    "orçamento de tokens do build_context",
    "fila de toque claim",
    "hook de commit do git",
    "busca híbrida RRF",
    "status.json last_error",
    "lembrete de busca nudge",
]


async def medir(limit: int | None, formato: str | None) -> list[int]:
    servidor = build_server(load_config(), allow_write=False, profile="slim")
    args_extra: dict[str, object] = {}
    if limit is not None:
        args_extra["limit"] = limit
    if formato is not None:
        args_extra["response_format"] = formato
    tokens = []
    for consulta in CONSULTAS:
        resposta = await servidor.call_tool("search_hybrid", {"query": consulta, **args_extra})
        tokens.append(count_tokens("".join(bloco.text for bloco in resposta.content)))
    return tokens


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None, help="resultados por busca (padrão do servidor: 5)")
    ap.add_argument("--format", choices=["concise", "detailed"], default=None)
    args = ap.parse_args()
    tokens = asyncio.run(medir(args.limit, args.format))
    print(f"busca slim: mediana {statistics.median(tokens):.0f} tokens, máximo {max(tokens)}; por consulta: {tokens}")


if __name__ == "__main__":
    main()

"""Mede o custo da primeira busca de um servidor MCP recém-iniciado (RAGX-0142, S9).

Sobe `ragx mcp serve` por stdio, mede o `initialize` e a primeira `search_hybrid`, com e sem
espera entre os dois (o aquecimento roda nesse intervalo). Imprime a mediana de N execuções.

    uv run python scripts/medir_mcp_frio.py --espera 5 --execucoes 5 [--projeto PASTA] [--sem-warmup]

Rode dentro (ou aponte `--projeto` para) um projeto já indexado. `--sem-warmup` liga
`RAGX_MCP_WARMUP=0` no servidor, para a linha de base.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path


async def uma_vez(projeto: Path, espera: float, sem_warmup: bool) -> tuple[float, float]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    if sem_warmup:
        env["RAGX_MCP_WARMUP"] = "0"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ragx.cli.main", "mcp", "serve"],
        cwd=str(projeto),
        env=env,
    )
    async with stdio_client(params) as (leitura, escrita), ClientSession(leitura, escrita) as sessao:
        t0 = time.perf_counter()
        await sessao.initialize()
        inicializar = (time.perf_counter() - t0) * 1000
        if espera:
            await asyncio.sleep(espera)
        t1 = time.perf_counter()
        await sessao.call_tool("search_hybrid", {"query": "como o contexto é montado dentro do orçamento"})
        primeira = (time.perf_counter() - t1) * 1000
    return inicializar, primeira


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--espera", type=float, default=5.0)
    ap.add_argument("--execucoes", type=int, default=5)
    ap.add_argument("--projeto", type=Path, default=Path.cwd())
    ap.add_argument("--sem-warmup", action="store_true")
    a = ap.parse_args()
    medidas = [asyncio.run(uma_vez(a.projeto, a.espera, a.sem_warmup)) for _ in range(a.execucoes)]
    print(f"initialize_ms={statistics.median(m[0] for m in medidas):.0f}")
    print(f"primeira_busca_ms={statistics.median(m[1] for m in medidas):.0f}")
    print("amostras:", [(round(i), round(p)) for i, p in medidas])


if __name__ == "__main__":
    main()

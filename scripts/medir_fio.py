"""Mede o que o cliente MCP recebe de verdade: o texto da resposta de uma ferramenta.

O que conta para o orçamento do agente não é o `estimated_tokens` que o servidor
declara, é o texto que chega ao contexto. Este script sobe o servidor em
processo, chama a ferramenta pelo mesmo caminho do cliente (`call_tool`) e conta
os caracteres e os tokens do que sairia no fio.

    uv run python scripts/medir_fio.py --tool build_context --tokens 3000
    uv run python scripts/medir_fio.py --tool search_hybrid --query "gate de segurança"
    uv run python scripts/medir_fio.py --tool tools_list          # custo fixo das ferramentas
    uv run python scripts/medir_fio.py --tool get_dictionary --arg section=services

Contadores: o do RAGX (`count_tokens`, que já usa `tiktoken` quando instalado), o
`tiktoken` direto (cl100k) e `chars/4`, que é o que a auditoria usou nas ferramentas. Nenhum dos dois é o tokenizador do Claude: servem para
comparar antes e depois, não como verdade absoluta.

Usado pelas tarefas RAGX-0154, 0155, 0157 e 0165.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ragx.config import load_config
from ragx.mcp.server import build_server
from ragx.tokens import count_tokens


def _tiktoken(text: str) -> int | None:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return None


def _texto_da_resposta(resultado: Any) -> str:
    """O texto que o cliente recebe: os blocos de conteúdo, concatenados."""
    return "".join(getattr(b, "text", "") or "" for b in resultado.content)


def _estrutura(resultado: Any) -> Any:
    """O `structuredContent`: o SDK o envia ALÉM do texto, e conta como outro tanto no fio."""
    return getattr(resultado, "structured_content", None)


async def _medir(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_config(Path(args.root) if args.root else None)
    server = build_server(cfg, allow_write=False)

    if args.tool == "tools_list":
        tools = await server.list_tools()
        itens = [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
            for t in tools
        ]
        texto = json.dumps(itens, ensure_ascii=False)
        # "chars_visiveis": o que o modelo lê (nome + descrição + schema de entrada)
        saida = [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema,
             **({"outputSchema": t.output_schema} if getattr(t, "output_schema", None) else {})}
            for t in tools
        ]
        com_saida = json.dumps(saida, ensure_ascii=False)
        return {"tool": "tools_list", "ferramentas": len(tools), "texto": texto,
                "texto_com_outputschema": com_saida}

    argumentos: dict[str, Any] = {}
    if args.query:
        argumentos["query"] = args.query
    if args.tokens:
        argumentos["tokens"] = args.tokens
    for par in args.arg or []:
        chave, _, valor = par.partition("=")
        argumentos[chave] = int(valor) if valor.isdigit() else valor
    if args.tool in ("build_context", "search_hybrid", "search_knowledge") and "query" not in argumentos:
        argumentos["query"] = "como o security gate decide bloquear um arquivo"

    resultado = await server.call_tool(args.tool, argumentos)
    texto = _texto_da_resposta(resultado)
    estrutura = _estrutura(resultado)
    out: dict[str, Any] = {"tool": args.tool, "argumentos": argumentos, "texto": texto}
    if estrutura is not None:
        out["structured"] = json.dumps(estrutura, ensure_ascii=False)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tool", required=True)
    ap.add_argument("--query")
    ap.add_argument("--tokens", type=int)
    ap.add_argument("--arg", action="append", help="chave=valor (repetível)")
    ap.add_argument("--root", help="raiz do projeto (padrão: o diretório atual)")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    args = ap.parse_args()

    r = asyncio.run(_medir(args))
    texto: str = r["texto"]
    linhas = {
        "tool": r["tool"],
        "chars": len(texto),
        "tokens_ragx": count_tokens(texto),
        "tokens_chars4": len(texto) // 4,
        "tokens_tiktoken": _tiktoken(texto),
    }
    if "ferramentas" in r:
        linhas["ferramentas"] = r["ferramentas"]
        linhas["tokens_com_outputschema_tiktoken"] = _tiktoken(r["texto_com_outputschema"])
    if "structured" in r:
        linhas["structured_chars"] = len(r["structured"])
        linhas["structured_tokens_tiktoken"] = _tiktoken(r["structured"])
    # Para build_context: o que o servidor DECLAROU, ao lado do que saiu.
    try:
        dados = json.loads(texto)
        data = dados.get("data", {}) if isinstance(dados, dict) else {}
        if isinstance(data, dict) and "estimated_tokens" in data:
            linhas["estimated_tokens_declarado"] = data["estimated_tokens"]
            linhas["budget"] = data.get("budget")
            linhas["tem_fragments"] = "fragments" in data
            linhas["tem_markdown"] = "markdown" in data
    except ValueError:
        pass
    if args.json:
        print(json.dumps(linhas, ensure_ascii=False))
    else:
        for k, v in linhas.items():
            print(f"{k:34} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

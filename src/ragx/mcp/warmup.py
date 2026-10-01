"""Aquecimento do servidor MCP (RAGX-0142).

A primeira `search_hybrid` de cada processo custava 3,0 a 3,3 s: construir o embedder (modelo ONNX,
tokenizer, imports) e o `tiktoken`. O servidor vive a sessão inteira e fica ocioso depois do
`initialize`; este módulo usa esse tempo, numa thread `daemon`, para deixar tudo pronto antes da
primeira pergunta.

Nunca atrasa nem derruba o servidor: cada passo é isolado, o erro vai para `.ragx/logs/errors.log` e
não propaga. E só aquece pasta com índice: o servidor registrado globalmente numa pasta que não é
projeto RAGX não carrega 680 MB à toa.
"""

from __future__ import annotations

import threading
from typing import Any

from ragx.diagnostics import log_exception


def _passos(cfg: Any) -> list[tuple[str, Any]]:
    def embedder() -> None:
        from ragx.embeddings import build_embedder

        # uma consulta de verdade: o primeiro `embed_query` também paga (sessão ONNX, conexão)
        build_embedder(cfg).embed_query("ragx")

    def contador() -> None:
        from ragx.tokens import count_tokens

        count_tokens("ragx")

    def indice() -> None:
        from ragx.embeddings import embedder_id
        from ragx.storage.db import open_db
        from ragx.storage.vectors import load_index

        with open_db(cfg.db_path, read_only=True) as conn:
            load_index(conn, embedder_id(cfg))

    return [("embedder", embedder), ("contador", contador), ("indice", indice)]


def warm(cfg: Any) -> None:
    """Executa os passos de aquecimento; cada falha é registrada e ignorada."""
    for nome, passo in _passos(cfg):
        try:
            passo()
        except Exception as exc:
            log_exception(cfg.state_dir, f"mcp.warmup.{nome}", exc)


def start(cfg: Any) -> threading.Thread | None:
    """Dispara `warm` numa thread `daemon`. `None` se não deve aquecer (sem índice ou desligado)."""
    if not cfg.mcp.warmup or not cfg.db_path.exists():
        return None
    thread = threading.Thread(target=warm, args=(cfg,), name="ragx-warmup", daemon=True)
    thread.start()
    return thread

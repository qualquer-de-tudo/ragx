"""Versão e preenchimento do prefixo de contexto dos chunks (RAGX-0166).

O contexto de um chunk é função PURA de dados que já estão no banco (caminho do documento, tipo, símbolo, título e o próprio
conteúdo, que o Security Gate já liberou). Por isso, ao subir a `CONTEXT_VERSION` (ou ao migrar um banco antigo) não é preciso
reler arquivo nenhum nem reindexar: `ensure_context` recalcula o contexto de todos os chunks a partir do banco e invalida os
vetores, que foram feitos com o texto antigo.
"""

from __future__ import annotations

import sqlite3

from ragx.core.models import Chunk, ChunkKind
from ragx.indexing.chunkers import build_context_text
from ragx.storage.db import get_meta, set_meta

#: Sobe quando `build_context_text` muda de forma que o texto embutido ou o FTS mude: invalida vetores e refaz o contexto.
CONTEXT_VERSION = "1"
META_KEY = "context_version"


def ensure_context(conn: sqlite3.Connection) -> int:
    """Se a versão gravada difere da atual, refaz `chunks.context` e apaga os vetores. Devolve quantos chunks atualizou.

    Idempotente e barato quando já está em dia (uma leitura de `meta`). Não lê arquivo do projeto.
    """
    if get_meta(conn, META_KEY) == CONTEXT_VERSION:
        return 0
    rows = conn.execute(
        """SELECT c.id, d.rel_path, c.kind, c.symbol, c.heading_path, c.content, c.context
           FROM chunks c JOIN documents d ON d.id = c.document_id"""
    ).fetchall()
    mudou: list[tuple[str, str]] = []
    for r in rows:
        stub = Chunk(
            id=r["id"], document_id="", ordinal=0, kind=ChunkKind(r["kind"]), start_line=0, end_line=0,
            content=r["content"], content_hash="", token_count=0, symbol=r["symbol"], heading_path=r["heading_path"],
        )
        novo = build_context_text(r["rel_path"], stub)
        if novo != r["context"]:
            mudou.append((novo, r["id"]))
    if mudou:
        conn.executemany("UPDATE chunks SET context = ? WHERE id = ?", mudou)  # os gatilhos refazem o FTS
    # os vetores já gravados foram embutidos com o texto antigo: voltam para a fila do embedder
    conn.execute("DELETE FROM embeddings")
    set_meta(conn, META_KEY, CONTEXT_VERSION)
    conn.commit()
    return len(mudou)

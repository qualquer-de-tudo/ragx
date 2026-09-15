"""Geração de embeddings dos chunks já indexados.

Etapa separada do pipeline de propósito: embedder fora do ar não pode derrubar
a indexação. Os chunks ficam gravados sem vetor e `ragx index --embed-only`
completa depois (ADR-0004).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ragx.config import Config
from ragx.embeddings import build_embedder
from ragx.embeddings.base import EmbeddingCache
from ragx.indexing.chunkers import context_prefix
from ragx.storage.vectors import (
    embedding_count,
    missing_chunk_ids,
    register_model,
    store_vectors,
)


@dataclass
class EmbedReport:
    model_id: str = ""
    pending: int = 0
    embedded: int = 0
    from_cache: int = 0
    total: int = 0
    replaced_model: int = 0
    error: str | None = None


def embed_pending(
    cfg: Config,
    conn: sqlite3.Connection,
    progress: Callable[[int, int], None] | None = None,
) -> EmbedReport:
    report = EmbedReport()
    try:
        embedder = build_embedder(cfg)
    except Exception as exc:
        report.error = str(exc)
        return report

    # Sondagem barata ANTES de qualquer lote. Sem isto, numa máquina sem o daemon
    # cada indexação paga 3 retries com backoff por lote — dezenas de segundos
    # para chegar à mesma conclusão que uma checagem de 2 s dá.
    probe = getattr(embedder, "available", None)
    if probe is not None and not probe():
        report.error = (
            f"embedder {embedder.id} indisponível\n"
            "  → inicie o daemon: ollama serve\n"
            "  → ou use: ragx config set embedding.provider hashing"
        )
        return report

    report.model_id = embedder.id
    vdim = min(cfg.embedding.versioned_dim or embedder.dim, embedder.dim)
    register_model(conn, embedder.id, embedder.dim, vdim, cfg.embedding.versioned_quant)

    # Vetores de modelo anterior ficam órfãos e INCOMPARÁVEIS com os novos.
    # Deixá-los no banco fez `dedupe_near` comparar 384 com 256 dimensões.
    stale = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM embedding_models WHERE id != ?", (embedder.id,)
        )
    ]
    if stale:
        ph = ",".join("?" * len(stale))
        n = conn.execute(
            f"DELETE FROM embeddings WHERE model_id IN ({ph})", stale
        ).rowcount
        conn.execute(f"DELETE FROM embedding_models WHERE id IN ({ph})", stale)
        conn.commit()
        report.replaced_model = n or 0

    pending = missing_chunk_ids(conn, embedder.id)
    report.pending = len(pending)
    if not pending:
        report.total = embedding_count(conn)
        return report

    cache = EmbeddingCache(cfg.state_dir / "cache", embedder.id, cfg.embedding.cache)
    paths = _paths_for(conn, [cid for cid, _, _ in pending])

    todo: list[tuple[str, str, str]] = []
    ready: list[tuple[str, np.ndarray]] = []
    for cid, chash, content in pending:
        cached = cache.get(chash)
        if cached is not None and cached.size == embedder.dim:
            ready.append((cid, cached))
            report.from_cache += 1
        else:
            todo.append((cid, chash, content))

    batch = max(cfg.embedding.batch, 1)
    done = 0
    try:
        for i in range(0, len(todo), batch):
            window = todo[i : i + batch]
            # Prefixo de contexto entra SÓ no embedding, nunca em chunks.content.
            texts = [
                _prefixed(paths.get(cid, ""), content, cid, conn) for cid, _h, content in window
            ]
            vecs = embedder.embed_documents(texts)
            for (cid, chash, _c), vec in zip(window, vecs, strict=True):
                cache.put(chash, vec)
                ready.append((cid, vec))
            done += len(window)
            if progress:
                progress(done, len(todo))
    except Exception as exc:
        report.error = str(exc)

    if ready:
        report.embedded = store_vectors(conn, embedder.id, ready, vdim)
    report.total = embedding_count(conn)
    return report


def _paths_for(conn: sqlite3.Connection, chunk_ids: list[str]) -> dict[str, str]:
    if not chunk_ids:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(chunk_ids), 500):
        window = chunk_ids[i : i + 500]
        ph = ",".join("?" * len(window))
        for r in conn.execute(
            f"""SELECT c.id, d.rel_path FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id IN ({ph})""",
            window,
        ):
            out[r["id"]] = r["rel_path"]
    return out


def _prefixed(rel_path: str, content: str, chunk_id: str, conn: sqlite3.Connection) -> str:
    r = conn.execute(
        "SELECT kind, symbol, heading_path FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    if r is None:
        return content
    from ragx.core.models import Chunk, ChunkKind

    stub = Chunk(
        id=chunk_id, document_id="", ordinal=0, kind=ChunkKind(r["kind"]),
        start_line=0, end_line=0, content=content, content_hash="", token_count=0,
        symbol=r["symbol"], heading_path=r["heading_path"],
    )
    return context_prefix(rel_path, stub)

"""Busca vetorial: força bruta exata em NumPy, em dois estágios.

[1] grosseira sobre int8@versioned_dim — sempre disponível, inclusive logo
    após um git clone, sem embedder e sem rede
[2] rescoring com float32@dim — só quando os vetores locais existem

Ver ADR-0003 e ADR-0010.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np

from ragx.embeddings.base import dequantize, l2_normalize, pack_f32, quantize, unpack_f32
from ragx.storage.db import utcnow

# Acima deste volume, força bruta deixa de ser a escolha certa (ADR-0003).
ANN_THRESHOLD = 100_000


@dataclass
class VectorIndex:
    """Matriz carregada uma vez por processo, invalidada pela versão do índice."""

    ids: list[str] = field(default_factory=list)
    coarse: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    full: np.ndarray | None = None
    model_id: str = ""
    dim: int = 0
    versioned_dim: int = 0

    @property
    def size(self) -> int:
        return len(self.ids)

    @property
    def has_full(self) -> bool:
        return self.full is not None

    def search(
        self, query: np.ndarray, k: int, mask: np.ndarray | None = None, rescore: bool = True
    ) -> list[tuple[str, float]]:
        if self.size == 0:
            return []

        idx = np.arange(self.size)
        if mask is not None:
            idx = idx[mask]
            if idx.size == 0:
                return []

        # [1] grosseira
        q_coarse = l2_normalize(np.asarray(query, dtype=np.float32)[: self.versioned_dim])
        coarse_scores = self.coarse[idx] @ q_coarse

        # Pede mais candidatos do que o necessário para o rescoring ter o que refinar.
        want = min(len(idx), max(k * 10, 100))
        top = idx[np.argpartition(-coarse_scores, want - 1)[:want]] if len(idx) > want else idx

        # [2] rescoring exato
        if rescore and self.full is not None:
            q_full = l2_normalize(np.asarray(query, dtype=np.float32)[: self.dim])
            scores = self.full[top] @ q_full
        else:
            pos = {v: i for i, v in enumerate(idx)}
            scores = coarse_scores[[pos[t] for t in top]]

        order = np.argsort(-scores)[:k]
        return [(self.ids[top[o]], float(scores[o])) for o in order]


def load_index(conn: sqlite3.Connection, model_id: str | None = None) -> VectorIndex:
    model = _resolve_model(conn, model_id)
    if model is None:
        return VectorIndex()

    rows = conn.execute(
        "SELECT chunk_id, vector, vector_q, q_scale, q_offset FROM embeddings WHERE model_id = ?",
        (model["id"],),
    ).fetchall()
    if not rows:
        return VectorIndex(model_id=model["id"], dim=model["dim"],
                           versioned_dim=model["versioned_dim"])

    ids = [r["chunk_id"] for r in rows]
    coarse = np.vstack(
        [l2_normalize(dequantize(r["vector_q"], r["q_scale"], r["q_offset"])) for r in rows]
    )
    full = None
    if all(r["vector"] is not None for r in rows):
        full = np.vstack([unpack_f32(r["vector"]) for r in rows])

    return VectorIndex(
        ids=ids, coarse=coarse, full=full,
        model_id=model["id"], dim=model["dim"], versioned_dim=model["versioned_dim"],
    )


def _resolve_model(conn: sqlite3.Connection, model_id: str | None) -> dict | None:
    if model_id:
        r = conn.execute("SELECT * FROM embedding_models WHERE id = ?", (model_id,)).fetchone()
    else:
        r = conn.execute(
            "SELECT * FROM embedding_models ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return dict(r) if r else None


def register_model(
    conn: sqlite3.Connection, model_id: str, dim: int, versioned_dim: int, quant: str = "int8"
) -> None:
    conn.execute(
        """INSERT INTO embedding_models(id, dim, versioned_dim, quant, normalized, created_at)
           VALUES (?,?,?,?,1,?)
           ON CONFLICT(id) DO UPDATE SET dim=excluded.dim,
             versioned_dim=excluded.versioned_dim, quant=excluded.quant""",
        (model_id, dim, versioned_dim, quant, utcnow()),
    )


def store_vectors(
    conn: sqlite3.Connection,
    model_id: str,
    items: list[tuple[str, np.ndarray]],
    versioned_dim: int,
    keep_full: bool = True,
) -> int:
    now = utcnow()
    rows = []
    for chunk_id, vec in items:
        q = quantize(vec, versioned_dim)
        rows.append(
            (chunk_id, model_id, pack_f32(vec) if keep_full else None,
             q.data, q.scale, q.offset, now)
        )
    conn.executemany(
        """INSERT INTO embeddings
           (chunk_id, model_id, vector, vector_q, q_scale, q_offset, created_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(chunk_id, model_id) DO UPDATE SET
             vector=excluded.vector, vector_q=excluded.vector_q,
             q_scale=excluded.q_scale, q_offset=excluded.q_offset""",
        rows,
    )
    return len(rows)


def missing_chunk_ids(conn: sqlite3.Connection, model_id: str) -> list[tuple[str, str, str]]:
    """(chunk_id, content_hash, content) dos chunks ainda sem vetor."""
    return [
        (r["id"], r["content_hash"], r["content"])
        for r in conn.execute(
            """SELECT c.id, c.content_hash, c.content FROM chunks c
               LEFT JOIN embeddings e ON e.chunk_id = c.id AND e.model_id = ?
               WHERE e.chunk_id IS NULL""",
            (model_id,),
        )
    ]


def embedding_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])

"""Busca vetorial: força bruta exata em NumPy, em dois estágios.

[1] grosseira sobre int8@versioned_dim — sempre disponível, inclusive logo
    após um git clone, sem embedder e sem rede
[2] rescoring com float32@dim — só quando os vetores locais existem

Ver ADR-0003 e ADR-0010.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field

import numpy as np

from ragx.embeddings.base import dequantize, l2_normalize, pack_f32, quantize, unpack_f32
from ragx.storage.db import utcnow

# Acima deste volume, força bruta deixa de ser a escolha certa (ADR-0003).
ANN_THRESHOLD = 100_000


@dataclass
class VectorIndex:
    """Matriz carregada uma vez por processo, invalidada pela geração `vec_gen`.

    O objeto devolvido por `load_index` é COMPARTILHADO entre chamadas: ninguém
    o altera (as matrizes são somente leitura de propósito).
    """

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


# Cache por processo: (caminho do banco, modelo) -> (estado, índice). O servidor
# MCP vive a sessão inteira; carregar a matriz a cada busca custava 50-80 ms, cerca
# de 75% do `search_hybrid` quente (RAGX-0134).
_CACHE: dict[tuple[str, str], tuple[tuple[int, int, int], VectorIndex]] = {}
_CACHE_LOCK = threading.Lock()
_MAX_CACHED = 4  # bancos; um modelo por banco


def reset_vector_cache() -> None:
    """Descarta o cache. Para teste e para troca de banco em voo."""
    with _CACHE_LOCK:
        _CACHE.clear()


def vec_generation(conn: sqlite3.Connection) -> int | None:
    """A geração dos vetores (`meta('vec_gen')`), mantida por gatilhos em `embeddings`.

    `None` quando a chave não existe (banco de um esquema anterior aberto só para
    leitura): quem recebe `None` não pode confiar em cache.
    """
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'vec_gen'").fetchone()
        return int(row[0]) if row is not None else None
    except (sqlite3.Error, TypeError, ValueError):
        return None


def _db_path(conn: sqlite3.Connection) -> str | None:
    for r in conn.execute("PRAGMA database_list"):
        if r[1] == "main":
            return str(r[2]) or None  # banco em memória não tem caminho
    return None


def load_index(conn: sqlite3.Connection, model_id: str | None = None) -> VectorIndex:
    model = _resolve_model(conn, model_id)
    if model is None:
        return VectorIndex()

    # A geração é lida ANTES das linhas: se um escritor confirmar no meio, o pior
    # caso é a próxima chamada ver a geração nova e recarregar.
    gen = vec_generation(conn)
    path = _db_path(conn)
    chave = (path or "", model["id"])
    estado = (gen if gen is not None else -1, model["dim"], model["versioned_dim"])
    cacheavel = gen is not None and path is not None and not conn.in_transaction
    if cacheavel:
        with _CACHE_LOCK:
            hit = _CACHE.get(chave)
        if hit is not None and hit[0] == estado:
            return hit[1]

    idx = _carregar(conn, model)
    if cacheavel:
        with _CACHE_LOCK:
            if chave not in _CACHE and len(_CACHE) >= _MAX_CACHED:
                _CACHE.pop(next(iter(_CACHE)))  # FIFO: o dict preserva a ordem de inserção
            _CACHE[chave] = (estado, idx)
    return idx


def _carregar(conn: sqlite3.Connection, model: dict) -> VectorIndex:
    rows = conn.execute(
        "SELECT chunk_id, vector, vector_q, q_scale, q_offset FROM embeddings WHERE model_id = ?",
        (model["id"],),
    ).fetchall()
    if not rows:
        return VectorIndex(model_id=model["id"], dim=model["dim"],
                           versioned_dim=model["versioned_dim"])

    n = len(rows)
    ids = [r["chunk_id"] for r in rows]
    coarse = _coarse_matrix(rows, model["versioned_dim"])
    full = None
    if all(r["vector"] is not None for r in rows):
        blob = b"".join(r["vector"] for r in rows)
        if len(blob) == n * model["dim"] * 4:
            full = np.frombuffer(blob, dtype=np.float32).reshape(n, model["dim"])
        else:  # linhas de tamanhos diferentes: o caminho por linha decide (e reclama, se for o caso)
            full = np.vstack([unpack_f32(r["vector"]) for r in rows])
    coarse.flags.writeable = False
    if full is not None:
        full.flags.writeable = False

    return VectorIndex(
        ids=ids, coarse=coarse, full=full,
        model_id=model["id"], dim=model["dim"], versioned_dim=model["versioned_dim"],
    )


def _coarse_matrix(rows: list[sqlite3.Row], vdim: int) -> np.ndarray:
    """int8 -> float32 normalizado, numa operação de matriz.

    Era `dequantize` + `l2_normalize` linha a linha em laço Python: 50-80 ms para
    7 mil vetores contra ~19 ms assim, com o mesmo resultado (diferença máxima
    ~6e-8). Se as linhas não têm o tamanho esperado, cai no caminho por linha.
    """
    n = len(rows)
    blob = b"".join(r["vector_q"] for r in rows)
    if len(blob) != n * vdim:
        return np.vstack(
            [l2_normalize(dequantize(r["vector_q"], r["q_scale"], r["q_offset"])) for r in rows]
        )
    m = np.frombuffer(blob, dtype=np.uint8).reshape(n, vdim).astype(np.float32)
    scale = np.fromiter((r["q_scale"] for r in rows), dtype=np.float32, count=n)
    offset = np.fromiter((r["q_offset"] for r in rows), dtype=np.float32, count=n)
    # No lugar, sem cópias: dequantiza e normaliza a mesma matriz.
    m *= scale[:, None]
    m += offset[:, None]
    norms = np.sqrt(np.einsum("ij,ij->i", m, m))
    norms[norms == 0.0] = 1.0
    m /= norms[:, None]
    return m


def _resolve_model(conn: sqlite3.Connection, model_id: str | None) -> dict | None:
    if model_id:
        r = conn.execute("SELECT * FROM embedding_models WHERE id = ?", (model_id,)).fetchone()
    else:
        r = conn.execute(
            "SELECT * FROM embedding_models ORDER BY created_at DESC, rowid DESC LIMIT 1"
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

"""Embedder: interface, quantização e cache.

Duas representações por chunk (ADR-0010):
  float32 @ dim           local, rescoring exato — 3.072 B
  int8    @ versioned_dim versionado no Git      —   256 B

A truncagem Matryoshka exige RENORMALIZAR depois de cortar: sem isso o produto
escalar deixa de aproximar cosseno e o ranking degrada em silêncio.
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    id: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class Quantized:
    data: bytes
    scale: float
    offset: float


def l2_normalize(v: np.ndarray) -> np.ndarray:
    if v.ndim == 1:
        n = float(np.linalg.norm(v))
        return v if n == 0.0 else (v / n).astype(np.float32)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (v / norms).astype(np.float32)


def quantize(vec: np.ndarray, versioned_dim: int) -> Quantized:
    """Trunca (Matryoshka), RENORMALIZA e quantiza em int8 por vetor."""
    t = np.asarray(vec, dtype=np.float32)[:versioned_dim]
    t = l2_normalize(t)
    lo = float(t.min())
    hi = float(t.max())
    scale = (hi - lo) / 255.0
    if scale <= 0.0:
        scale = 1e-8
    q = np.clip(np.round((t - lo) / scale), 0, 255).astype(np.uint8)
    return Quantized(q.tobytes(), scale, lo)


def dequantize(data: bytes, scale: float, offset: float) -> np.ndarray:
    q = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
    return q * scale + offset


def pack_f32(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack_f32(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


class EmbeddingCache:
    """Cache por content_hash: chunk movido ou arquivo renomeado não custa nada (RAGX-0146).

    Um SQLite por modelo em `<root>/emb/<modelo>.sqlite` (`content_hash` -> vetor float32), lido e escrito EM LOTE:
    antes era um arquivo por chunk (`mkdir` + `open` + `write`, 2,9 ms cada no Windows). Fica ao lado do índice, não
    dentro do `knowledge.db`: apagar o cache não toca o índice nem disputa a trava de escrita dele.

    Leitura de passagem: o que não está no SQLite é procurado no formato antigo (`emb/<modelo>/<hh>/<hash>.f32`) e
    IMPORTADO; não há migração em massa e a pasta antiga nunca é apagada. O cache é otimização, nunca motivo de falha:
    banco ilegível é renomeado para `.corrupt` e recriado, e erro de escrita vira "sem cache" naquela rodada.
    """

    def __init__(self, root: Path, model_id: str, enabled: bool = True):
        self.enabled = enabled
        safe = model_id.replace(":", "_").replace("/", "_")
        self.legacy_dir = Path(root) / "emb" / safe
        self.path = Path(root) / "emb" / f"{safe}.sqlite"
        #: chunks trazidos do formato antigo (por arquivo) nesta rodada
        self.imported = 0
        self._conn: sqlite3.Connection | None = None
        if enabled:
            self._open()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=5.0, check_same_thread=False)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS vecs "
                "(content_hash TEXT PRIMARY KEY, vec BLOB NOT NULL) WITHOUT ROWID"
            )
            conn.commit()
        except sqlite3.Error:
            conn.close()
            raise
        return conn

    def _open(self) -> None:
        try:
            self._conn = self._connect()
        except sqlite3.DatabaseError:
            # banco corrompido: guarda como `.corrupt` e recomeça (o cache é só otimização)
            try:
                self.path.replace(self.path.with_suffix(".sqlite.corrupt"))
                self._conn = self._connect()
            except (OSError, sqlite3.Error):
                self._conn = None
        except (OSError, sqlite3.Error):
            self._conn = None  # sem cache nesta rodada

    def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(sqlite3.Error):
                self._conn.close()
            self._conn = None

    def __enter__(self) -> EmbeddingCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_many(self, hashes: Sequence[str]) -> dict[str, np.ndarray]:
        """Vetores dos `hashes` que existem; janelas de 500 variáveis. O que falta é procurado no formato antigo."""
        if not self.enabled or not hashes:
            return {}
        out: dict[str, np.ndarray] = {}
        if self._conn is not None:
            try:
                for i in range(0, len(hashes), 500):
                    window = list(hashes[i : i + 500])
                    ph = ",".join("?" * len(window))
                    for h, blob in self._conn.execute(
                        f"SELECT content_hash, vec FROM vecs WHERE content_hash IN ({ph})", window
                    ):
                        out[h] = unpack_f32(blob)
            except sqlite3.Error:
                return {}
        if self.legacy_dir.is_dir():
            achados: list[tuple[str, np.ndarray]] = []
            for h in hashes:
                if h in out:
                    continue
                p = self.legacy_dir / h[:2] / f"{h}.f32"
                if p.is_file():
                    try:
                        vec = unpack_f32(p.read_bytes())
                    except OSError:
                        continue
                    out[h] = vec
                    achados.append((h, vec))
            if achados:
                self.imported += len(achados)
                self.put_many(achados)
        return out

    def put_many(self, items: Iterable[tuple[str, np.ndarray]]) -> None:
        """Grava vários numa transação. Falha de escrita não derruba a indexação."""
        if not self.enabled or self._conn is None:
            return
        rows = [(h, pack_f32(v)) for h, v in items]
        if not rows:
            return
        try:
            with self._conn:
                self._conn.executemany("INSERT OR REPLACE INTO vecs (content_hash, vec) VALUES (?, ?)", rows)
        except sqlite3.Error:
            pass

    def get(self, content_hash: str) -> np.ndarray | None:
        return self.get_many([content_hash]).get(content_hash)

    def put(self, content_hash: str, vec: np.ndarray) -> None:
        self.put_many([(content_hash, vec)])


def stable_hash_vector(text: str, dim: int) -> np.ndarray:
    """Vetor determinístico derivado do texto. Sem rede, sem modelo.

    Qualidade semântica é NULA — serve para testar o pipeline, jamais para medir
    qualidade de busca. Usa n-gramas de palavra para que textos parecidos fiquem
    ao menos parcialmente próximos.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = text.lower().split()
    for tok in tokens:
        h = int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0
        vec[(h >> 16) % dim] += 0.5
    for a, b in pairwise(tokens):
        h = int.from_bytes(
            hashlib.blake2b(f"{a} {b}".encode(), digest_size=8).digest(), "big"
        )
        vec[h % dim] += 0.75
    if not np.any(vec):
        vec[0] = 1.0
    return l2_normalize(vec)

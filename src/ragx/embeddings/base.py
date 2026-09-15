"""Embedder: interface, quantização e cache.

Duas representações por chunk (ADR-0010):
  float32 @ dim           local, rescoring exato — 3.072 B
  int8    @ versioned_dim versionado no Git      —   256 B

A truncagem Matryoshka exige RENORMALIZAR depois de cortar: sem isso o produto
escalar deixa de aproximar cosseno e o ranking degrada em silêncio.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
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
    """Cache por content_hash: chunk movido ou arquivo renomeado não custa nada."""

    def __init__(self, root: Path, model_id: str, enabled: bool = True):
        self.enabled = enabled
        safe = model_id.replace(":", "_").replace("/", "_")
        self.dir = Path(root) / "emb" / safe
        if enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, content_hash: str) -> Path:
        return self.dir / content_hash[:2] / f"{content_hash}.f32"

    def get(self, content_hash: str) -> np.ndarray | None:
        if not self.enabled:
            return None
        p = self._path(content_hash)
        if not p.is_file():
            return None
        try:
            return unpack_f32(p.read_bytes())
        except OSError:
            return None

    def put(self, content_hash: str, vec: np.ndarray) -> None:
        if not self.enabled:
            return
        p = self._path(content_hash)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(pack_f32(vec))
        except OSError:
            pass  # cache é otimização, nunca motivo de falha


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

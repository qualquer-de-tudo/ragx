"""Provider determinístico para testes. Sem rede, sem modelo, sem daemon."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ragx.embeddings.base import stable_hash_vector


class HashingEmbedder:
    def __init__(self, dim: int = 256):
        self.id = f"hashing:{dim}"
        self.dim = dim

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([stable_hash_vector(t, self.dim) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return stable_hash_vector(text, self.dim)

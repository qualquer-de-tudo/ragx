"""Provider Ollama. Nenhum byte do projeto sai da máquina (ADR-0004)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Sequence

import numpy as np

from ragx.core.errors import EnvError
from ragx.embeddings.base import l2_normalize

# nomic-embed-text foi treinado com prefixos assimétricos. Sem eles a qualidade
# cai visivelmente — por isso é responsabilidade do provider, nunca do chamador.
_DOC_PREFIX = "search_document: "
_QUERY_PREFIX = "search_query: "
_PREFIXED_MODELS = ("nomic-embed-text",)


class OllamaEmbedder:
    def __init__(
        self,
        model: str = "nomic-embed-text",
        dim: int = 768,
        base_url: str = "http://localhost:11434",
        batch: int = 32,
        timeout_s: int = 60,
        retries: int = 3,
    ):
        self.id = f"ollama:{model}"
        self.model = model
        self.dim = dim
        self.base_url = base_url.rstrip("/")
        self.batch = batch
        self.timeout_s = timeout_s
        self.retries = retries
        self._prefixed = any(model.startswith(m) for m in _PREFIXED_MODELS)

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last = exc
                if attempt < self.retries - 1:
                    time.sleep(2**attempt * 0.5)
        raise EnvError(
            f"embedder indisponível em {self.base_url}: {last}\n"
            "  → inicie o daemon: ollama serve\n"
            "  → ou use: ragx config set embedding.provider hashing"
        )

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out: list[np.ndarray] = []
        for i in range(0, len(texts), self.batch):
            window = list(texts[i : i + self.batch])
            if self._prefixed:
                window = [_DOC_PREFIX + t for t in window]
            data = self._post({"model": self.model, "input": window})
            out.extend(np.asarray(e, dtype=np.float32) for e in data["embeddings"])
        return l2_normalize(np.vstack(out))

    def embed_query(self, text: str) -> np.ndarray:
        payload_text = _QUERY_PREFIX + text if self._prefixed else text
        data = self._post({"model": self.model, "input": [payload_text]})
        return l2_normalize(np.asarray(data["embeddings"][0], dtype=np.float32))

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as r:
                return self.model.split(":")[0] in r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

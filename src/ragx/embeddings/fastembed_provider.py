"""Provider fastembed — embeddings locais SEM daemon.

Alternativa ao Ollama quando não se quer (ou não se pode) rodar um serviço:
ONNX Runtime embarcado, modelo baixado uma vez e cacheado no projeto. Depois
do primeiro download, funciona offline.

Dependência opcional: `uv pip install "ragx[embed]"`.

Padrão multilíngue de propósito — o corpus típico aqui é documentação em
português misturada com código. Um modelo só-inglês perderia metade do sinal.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from ragx.core.errors import EnvError
from ragx.embeddings.base import l2_normalize

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Modelos que exigem prefixo de tarefa. Como no Ollama, a responsabilidade é do
# provider, nunca do chamador.
_E5_PREFIXES = {"query": "query: ", "passage": "passage: "}


class FastEmbedEmbedder:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dim: int = 384,
        cache_dir: Path | None = None,
        batch: int = 32,
    ):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EnvError(
                "provider 'fastembed' exige a dependência opcional:\n"
                '  → uv pip install "ragx[embed]"'
            ) from exc

        self.id = f"fastembed:{model}"
        self.model_name = model
        self.dim = dim
        self.batch = batch
        self._e5 = "e5" in model.lower()

        kwargs: dict[str, object] = {"model_name": model}
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            kwargs["cache_dir"] = str(cache_dir)
        try:
            self._model = TextEmbedding(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            raise EnvError(
                f"não foi possível carregar {model}: {exc}\n"
                "  → o primeiro uso baixa o modelo; verifique a conexão\n"
                "  → ou use: ragx config set embedding.provider hashing"
            ) from exc

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        payload = [f"{_E5_PREFIXES['passage']}{t}" for t in texts] if self._e5 else list(texts)
        return l2_normalize(np.vstack(list(self._model.embed(payload, batch_size=self.batch))))

    def embed_query(self, text: str) -> np.ndarray:
        payload = f"{_E5_PREFIXES['query']}{text}" if self._e5 else text
        vec = next(iter(self._model.embed([payload])))
        return l2_normalize(np.asarray(vec, dtype=np.float32))

    def available(self) -> bool:
        """O modelo já está carregado na construção — se chegou aqui, funciona."""
        return True

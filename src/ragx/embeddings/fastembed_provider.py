"""Provider fastembed — embeddings locais SEM daemon.

Alternativa ao Ollama quando não se quer (ou não se pode) rodar um serviço:
ONNX Runtime embarcado, modelo baixado uma vez e cacheado no projeto. Depois
do primeiro download, funciona offline.

Dependência opcional: `uv pip install "ragx[embed]"`.

Padrão multilíngue de propósito — o corpus típico aqui é documentação em
português misturada com código. Um modelo só-inglês perderia metade do sinal.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from ragx.core.errors import EnvError
from ragx.embeddings.base import l2_normalize

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

#: Mapa DECLARADO `modelo -> (prefixo da consulta, prefixo do documento)` (RAGX-0104). Modelos assimétricos
#: (`e5`, `nomic`) só sabem qual lado estão codificando pelo prefixo; sem ele são usados como se fossem simétricos
#: e metade do benefício some. A lista é explícita (nada de adivinhar pelo nome do modelo): modelo ausente roda SEM
#: prefixo, como o padrão `paraphrase-multilingual-MiniLM-L12-v2`, que é simétrico. Como no Ollama, a responsabilidade
#: é do provider, nunca do chamador.
PREFIXES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
    "intfloat/e5-small-v2": ("query: ", "passage: "),
    "intfloat/e5-base-v2": ("query: ", "passage: "),
    "intfloat/e5-large-v2": ("query: ", "passage: "),
    "nomic-ai/nomic-embed-text-v1": ("search_query: ", "search_document: "),
    "nomic-ai/nomic-embed-text-v1.5": ("search_query: ", "search_document: "),
    "nomic-ai/nomic-embed-text-v1.5-Q": ("search_query: ", "search_document: "),
}


def prefixes_for(model: str) -> tuple[str, str]:
    """`(consulta, documento)` declarados para o modelo; `("", "")` se não houver."""
    return PREFIXES.get(model, ("", ""))


def model_id(model: str) -> str:
    """O `id` do embedder, com o esquema de prefixos dentro (RAGX-0104).

    Modelo sem prefixo mantém o id de sempre (`fastembed:<modelo>`): os índices existentes continuam válidos. Com
    prefixo, o id leva um resumo dele (`fastembed:<modelo>#p<hash>`): trocar o mapa troca o id e invalida os vetores já
    gravados, que foram feitos com outro texto.
    """
    consulta, documento = prefixes_for(model)
    if not consulta and not documento:
        return f"fastembed:{model}"
    resumo = hashlib.sha256(f"{consulta}\x00{documento}".encode()).hexdigest()[:6]
    return f"fastembed:{model}#p{resumo}"


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

        self.id = model_id(model)
        self.model_name = model
        self.dim = dim
        self.batch = batch
        self._prefix_query, self._prefix_doc = prefixes_for(model)

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
        payload = [f"{self._prefix_doc}{t}" for t in texts] if self._prefix_doc else list(texts)
        return l2_normalize(np.vstack(list(self._model.embed(payload, batch_size=self.batch))))

    def embed_query(self, text: str) -> np.ndarray:
        payload = f"{self._prefix_query}{text}" if self._prefix_query else text
        vec = next(iter(self._model.embed([payload])))
        return l2_normalize(np.asarray(vec, dtype=np.float32))

    def available(self) -> bool:
        """O modelo já está carregado na construção — se chegou aqui, funciona."""
        return True

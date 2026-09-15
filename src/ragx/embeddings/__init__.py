"""Providers de embedding. A escolha é configuração, não código."""

from __future__ import annotations

from ragx.config import Config
from ragx.core.errors import UsageError
from ragx.embeddings.base import Embedder
from ragx.embeddings.hashing import HashingEmbedder
from ragx.embeddings.ollama import OllamaEmbedder


def build_embedder(cfg: Config) -> Embedder:
    p = cfg.embedding.provider
    if p == "hashing":
        return HashingEmbedder(dim=cfg.embedding.dim)
    if p == "ollama":
        return OllamaEmbedder(
            model=cfg.embedding.model,
            dim=cfg.embedding.dim,
            base_url=cfg.embedding.base_url,
            batch=cfg.embedding.batch,
            timeout_s=cfg.embedding.timeout_s,
        )
    if p == "fastembed":
        from ragx.embeddings.fastembed_provider import DEFAULT_MODEL, FastEmbedEmbedder

        # o modelo default do bloco [embedding] é do Ollama; se o usuário só
        # trocou o provider, usa o default do fastembed em vez de falhar
        model = cfg.embedding.model
        if model in ("nomic-embed-text", "", None):
            model = DEFAULT_MODEL
        return FastEmbedEmbedder(
            model=model,
            dim=cfg.embedding.dim,
            cache_dir=cfg.state_dir / "cache" / "models",
            batch=cfg.embedding.batch,
        )
    raise UsageError(
        f"provider de embedding desconhecido: {p!r} (use ollama | fastembed | hashing)"
    )


__all__ = ["Embedder", "HashingEmbedder", "OllamaEmbedder", "build_embedder"]

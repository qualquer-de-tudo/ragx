"""Providers de embedding. A escolha é configuração, não código."""

from __future__ import annotations

from ragx.config import Config
from ragx.core.errors import UsageError
from ragx.embeddings.base import Embedder
from ragx.embeddings.hashing import HashingEmbedder
from ragx.embeddings.ollama import OllamaEmbedder

#: Instâncias já construídas, por configuração de embedding.
#:
#: Construir o `FastEmbedEmbedder` carrega um modelo ONNX e custa 2,5–3,6 s;
#: embutir a consulta com ele pronto custa ~10 ms. Como `build_embedder` era
#: chamado a CADA busca — e duas vezes por `build_context` —, praticamente toda
#: a latência da busca semântica era carregar o modelo de novo.
#:
#: O ganho aparece em processo que vive: o servidor MCP, o `ragx watch`, a
#: indexação. Num comando de CLI de uma tacada só, o processo morre antes de
#: reaproveitar — e aí o cache não custa nada também.
_CACHE: dict[tuple[object, ...], Embedder] = {}

#: Teto de instâncias vivas. Na prática são uma ou duas; o limite existe para
#: que uma suíte que varre configurações não segure N modelos na memória.
_MAX_CACHE = 4


def _chave(cfg: Config) -> tuple[object, ...]:
    """O que, se mudar, exige um embedder diferente.

    `state_dir` entra porque é onde o fastembed guarda o modelo baixado: dois
    projetos com raízes diferentes não devem compartilhar instância, mesmo com
    o mesmo modelo.
    """
    e = cfg.embedding
    return (e.provider, e.model, e.dim, e.base_url, e.batch, e.timeout_s, str(cfg.state_dir))


def reset_embedder_cache() -> None:
    """Descarta as instâncias. Para teste e para troca de configuração em voo."""
    _CACHE.clear()


def build_embedder(cfg: Config) -> Embedder:
    chave = _chave(cfg)
    pronto = _CACHE.get(chave)
    if pronto is not None:
        return pronto

    embedder = _construir(cfg)
    if len(_CACHE) >= _MAX_CACHE:
        # FIFO: o dict preserva ordem de inserção desde o 3.7.
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[chave] = embedder
    return embedder


def _construir(cfg: Config) -> Embedder:
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


__all__ = [
    "Embedder",
    "HashingEmbedder",
    "OllamaEmbedder",
    "build_embedder",
    "reset_embedder_cache",
]

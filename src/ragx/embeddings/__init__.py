"""Providers de embedding. A escolha é configuração, não código."""

from __future__ import annotations

import os
import threading
from pathlib import Path

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

#: Uma trava por chave de configuração, e uma que guarda o dicionário delas. A thread de
#: aquecimento do servidor MCP (RAGX-0142) e a primeira busca esperam a MESMA construção em
#: vez de construir dois modelos (cerca de 1,4 GB). Construir de chaves diferentes não se serializa.
_LOCKS: dict[tuple[object, ...], threading.Lock] = {}
_GUARDA = threading.Lock()


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
    with _GUARDA:
        _CACHE.clear()
        _LOCKS.clear()


def build_embedder(cfg: Config) -> Embedder:
    chave = _chave(cfg)
    pronto = _CACHE.get(chave)
    if pronto is not None:
        return pronto

    with _GUARDA:
        trava = _LOCKS.setdefault(chave, threading.Lock())
    with trava:
        # quem esperou a trava encontra o embedder que a outra thread acabou de construir
        pronto = _CACHE.get(chave)
        if pronto is not None:
            return pronto
        embedder = _construir(cfg)
        with _GUARDA:
            if len(_CACHE) >= _MAX_CACHE:
                # FIFO: o dict preserva ordem de inserção desde o 3.7.
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[chave] = embedder
        return embedder


def legacy_models_dir(cfg: Config) -> Path:
    """Onde o fastembed guardava o modelo ANTES da RAGX-0153: uma cópia por projeto."""
    return cfg.state_dir / "cache" / "models"


def models_dir(cfg: Config) -> Path:
    """Pasta de modelos do fastembed (RAGX-0153).

    Um projeto cuja pasta antiga (`.ragx/cache/models`) já existe e NÃO está vazia continua usando a dele: quem já
    baixou não baixa de novo. Os demais compartilham `embedding.model_cache_dir` (padrão `~/.ragx/models`), então o
    segundo projeto novo não paga o download nem o disco (~240 MB) outra vez. Nada é movido, copiado ou apagado.
    """
    legado = legacy_models_dir(cfg)
    try:
        if legado.is_dir() and any(legado.iterdir()):
            return legado
    except OSError:
        pass
    configurado = cfg.embedding.model_cache_dir.strip()
    return Path(os.path.expanduser(configurado)) if configurado else legado


def _modelo_fastembed(cfg: Config) -> str:
    from ragx.embeddings.fastembed_provider import DEFAULT_MODEL

    # o modelo default do bloco [embedding] é do Ollama; se o usuário só
    # trocou o provider, usa o default do fastembed em vez de falhar
    model = cfg.embedding.model
    return DEFAULT_MODEL if model in ("nomic-embed-text", "", None) else model


def embedder_id(cfg: Config) -> str:
    """O `id` que `build_embedder(cfg)` teria, SEM construir o provider.

    Construir o `FastEmbedEmbedder` carrega o modelo ONNX (~2,85 s) e o
    `OllamaEmbedder` sonda o daemon (até 2 s). Quem só precisa do nome do modelo,
    como a indexação sem mudança, que descobre que não há chunk pendente, não
    deve pagar nada disso. A paridade com `Embedder.id` é protegida por teste.
    """
    p = cfg.embedding.provider
    if p == "hashing":
        return f"hashing:{cfg.embedding.dim}"
    if p == "ollama":
        return f"ollama:{cfg.embedding.model}"
    if p == "fastembed":
        from ragx.embeddings.fastembed_provider import model_id

        return model_id(_modelo_fastembed(cfg))
    raise UsageError(
        f"provider de embedding desconhecido: {p!r} (use ollama | fastembed | hashing)"
    )


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
        from ragx.embeddings.fastembed_provider import FastEmbedEmbedder

        return FastEmbedEmbedder(
            model=_modelo_fastembed(cfg),
            dim=cfg.embedding.dim,
            cache_dir=models_dir(cfg),
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
    "embedder_id",
    "legacy_models_dir",
    "models_dir",
    "reset_embedder_cache",
]

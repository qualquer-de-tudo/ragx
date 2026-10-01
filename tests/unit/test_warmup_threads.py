"""Construção do embedder e do contador seguras entre threads (RAGX-0142)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ragx import embeddings, tokens
from ragx.config import load_config

pytestmark = pytest.mark.unit


@pytest.fixture()
def cfg(tmp_path: Path):  # type: ignore[no-untyped-def]
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    embeddings.reset_embedder_cache()
    yield load_config(tmp_path)
    embeddings.reset_embedder_cache()


def _juntas(n: int, alvo) -> None:  # type: ignore[no-untyped-def]
    largada = threading.Barrier(n)

    def corre() -> None:
        largada.wait()
        alvo()

    threads = [threading.Thread(target=corre) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_oito_threads_constroem_uma_unica_instancia(cfg, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    construcoes: list[int] = []
    original = embeddings._construir

    def lenta(c):  # type: ignore[no-untyped-def]
        construcoes.append(1)
        time.sleep(0.2)  # a janela em que as outras threads chegam
        return original(c)

    monkeypatch.setattr(embeddings, "_construir", lenta)
    vistos: list[object] = []
    _juntas(8, lambda: vistos.append(embeddings.build_embedder(cfg)))
    assert len(construcoes) == 1
    assert len({id(e) for e in vistos}) == 1


def test_configuracoes_diferentes_nao_se_serializam(cfg, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """A trava é por chave: um modelo lento não segura a construção de outro."""
    outra = cfg.model_copy(deep=True)
    outra.embedding.dim = 32
    soltar = threading.Event()
    original = embeddings._construir

    def seletiva(c):  # type: ignore[no-untyped-def]
        if c.embedding.dim == 64:
            soltar.wait(5)
        return original(c)

    monkeypatch.setattr(embeddings, "_construir", seletiva)
    lenta = threading.Thread(target=lambda: embeddings.build_embedder(cfg))
    lenta.start()
    time.sleep(0.1)
    embeddings.build_embedder(outra)  # não pode ficar preso atrás da construção lenta
    assert lenta.is_alive()
    soltar.set()
    lenta.join()


def test_oito_threads_criam_um_unico_contador(monkeypatch: pytest.MonkeyPatch) -> None:
    criados: list[int] = []

    def lento(prefer: str = "auto"):  # type: ignore[no-untyped-def]
        criados.append(1)
        time.sleep(0.2)
        return tokens.HeuristicCounter()

    monkeypatch.setattr(tokens, "_default", None)
    monkeypatch.setattr(tokens, "get_counter", lento)
    _juntas(8, lambda: tokens.count_tokens("ragx"))
    assert len(criados) == 1

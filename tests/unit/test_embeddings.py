from __future__ import annotations

import numpy as np
import pytest

from ragx.embeddings.base import (
    dequantize,
    l2_normalize,
    pack_f32,
    quantize,
    stable_hash_vector,
    unpack_f32,
)
from ragx.embeddings.hashing import HashingEmbedder

pytestmark = pytest.mark.unit


def test_normalizacao_l2() -> None:
    v = np.array([3.0, 4.0], dtype=np.float32)
    assert abs(float(np.linalg.norm(l2_normalize(v))) - 1.0) < 1e-6


def test_normalizacao_de_vetor_zero_nao_quebra() -> None:
    assert not np.isnan(l2_normalize(np.zeros(8, dtype=np.float32))).any()


def test_quantizacao_reduz_para_1_byte_por_dimensao() -> None:
    v = l2_normalize(np.random.RandomState(0).randn(768).astype(np.float32))
    q = quantize(v, 256)
    assert len(q.data) == 256, "int8@256 deve ocupar exatamente 256 bytes"


def test_quantizacao_preserva_a_direcao() -> None:
    """Se o cosseno não sobrevivesse, o ranking degradaria em silêncio."""
    rs = np.random.RandomState(1)
    v = l2_normalize(rs.randn(768).astype(np.float32))
    q = quantize(v, 256)
    recon = l2_normalize(dequantize(q.data, q.scale, q.offset))
    truncado = l2_normalize(v[:256])
    assert float(recon @ truncado) > 0.99


def test_renormalizacao_apos_truncar() -> None:
    """Sem renormalizar, o produto escalar deixa de aproximar cosseno."""
    v = l2_normalize(np.random.RandomState(2).randn(768).astype(np.float32))
    q = quantize(v, 128)
    recon = dequantize(q.data, q.scale, q.offset)
    assert abs(float(np.linalg.norm(recon)) - 1.0) < 0.05


def test_quantizacao_de_vetor_constante_nao_divide_por_zero() -> None:
    q = quantize(np.full(64, 0.125, dtype=np.float32), 64)
    assert q.scale > 0 and len(q.data) == 64


def test_round_trip_float32() -> None:
    v = np.random.RandomState(3).randn(64).astype(np.float32)
    assert np.allclose(unpack_f32(pack_f32(v)), v)


def test_hashing_e_deterministico() -> None:
    a = stable_hash_vector("autenticacao via SSO", 128)
    b = stable_hash_vector("autenticacao via SSO", 128)
    assert np.array_equal(a, b)


def test_hashing_distingue_textos() -> None:
    a = stable_hash_vector("autenticacao", 256)
    b = stable_hash_vector("pagamento recorrente", 256)
    assert float(a @ b) < 0.5


def test_hashing_embedder_shape() -> None:
    e = HashingEmbedder(dim=64)
    m = e.embed_documents(["a", "b", "c"])
    assert m.shape == (3, 64)
    assert e.embed_query("a").shape == (64,)
    assert e.embed_documents([]).shape == (0, 64)


def test_ollama_aplica_prefixos_de_tarefa() -> None:
    """nomic-embed-text exige search_document:/search_query:. É responsabilidade
    do provider, nunca do chamador."""
    from ragx.embeddings.ollama import OllamaEmbedder

    e = OllamaEmbedder(model="nomic-embed-text", dim=4)
    enviados: list[dict] = []
    e._post = lambda payload: (  # type: ignore[method-assign]
        enviados.append(payload),
        {"embeddings": [[1.0, 0.0, 0.0, 0.0] for _ in payload["input"]]},
    )[1]

    e.embed_documents(["x"])
    assert enviados[-1]["input"][0].startswith("search_document: ")
    e.embed_query("y")
    assert enviados[-1]["input"][0].startswith("search_query: ")


def test_ollama_sem_prefixo_para_outro_modelo() -> None:
    from ragx.embeddings.ollama import OllamaEmbedder

    e = OllamaEmbedder(model="mxbai-embed-large", dim=4)
    enviados: list[dict] = []
    e._post = lambda payload: (  # type: ignore[method-assign]
        enviados.append(payload),
        {"embeddings": [[1.0, 0.0, 0.0, 0.0]]},
    )[1]
    e.embed_query("y")
    assert enviados[-1]["input"][0] == "y"

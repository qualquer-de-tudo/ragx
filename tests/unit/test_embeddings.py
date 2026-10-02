from __future__ import annotations

from typing import ClassVar

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


@pytest.mark.parametrize(
    "provider", ["hashing", "ollama", "fastembed"]
)
def test_embedder_id_nao_diverge_do_embedder_construido(provider: str) -> None:
    """`embedder_id` responde sem construir o modelo (RAGX-0130); se divergisse
    do `id` do provider, os vetores seriam gravados sob um nome e procurados
    sob outro."""
    from ragx.config import Config
    from ragx.embeddings import build_embedder, embedder_id, reset_embedder_cache

    if provider == "fastembed":
        pytest.importorskip("fastembed")
    cfg = Config()
    cfg.embedding.provider = provider
    cfg.embedding.dim = 384 if provider == "fastembed" else 64
    reset_embedder_cache()
    try:
        emb = build_embedder(cfg)
        assert embedder_id(cfg) == emb.id
        assert cfg.embedding.dim == emb.dim
    finally:
        reset_embedder_cache()


# ── pasta de modelos do fastembed (RAGX-0153) ───────────────────────────
def _cfg_modelos(tmp_path, extra: str = ""):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "fastembed"\ndim = 384\n' + extra,
        encoding="utf-8",
    )
    from ragx.config import load_config

    return load_config(tmp_path)


def test_models_dir_sem_cache_legado_usa_a_pasta_do_usuario(tmp_path) -> None:
    import os
    from pathlib import Path

    from ragx.embeddings import models_dir

    cfg = _cfg_modelos(tmp_path)
    assert cfg.embedding.model_cache_dir == "~/.ragx/models"
    esperado = Path(os.path.expanduser("~/.ragx/models"))
    assert models_dir(cfg) == esperado
    # o HOME redirecionado de `tests/conftest.py` é o que vale, nunca o da pessoa
    assert str(esperado).startswith(os.path.expanduser("~"))
    assert tmp_path not in models_dir(cfg).parents


def test_models_dir_com_cache_legado_vazio_ou_ausente_usa_a_do_usuario(tmp_path) -> None:
    from ragx.embeddings import legacy_models_dir, models_dir

    cfg = _cfg_modelos(tmp_path)
    assert models_dir(cfg) != legacy_models_dir(cfg)  # ausente
    legacy_models_dir(cfg).mkdir(parents=True)
    assert models_dir(cfg) != legacy_models_dir(cfg)  # existe, mas vazia


def test_models_dir_com_cache_legado_nao_vazio_continua_no_do_projeto(tmp_path) -> None:
    from ragx.embeddings import legacy_models_dir, models_dir

    cfg = _cfg_modelos(tmp_path)
    (legacy_models_dir(cfg) / "models--x").mkdir(parents=True)
    assert models_dir(cfg) == legacy_models_dir(cfg)


def test_models_dir_por_configuracao_e_por_variavel_de_ambiente(tmp_path, monkeypatch) -> None:
    from ragx.config import load_config
    from ragx.embeddings import models_dir

    cfg = _cfg_modelos(tmp_path / "p1", f'model_cache_dir = "{(tmp_path / "meus-modelos").as_posix()}"\n')
    assert models_dir(cfg) == tmp_path / "meus-modelos"

    monkeypatch.setenv("RAGX_EMBEDDING_MODEL_CACHE_DIR", str(tmp_path / "do-ambiente"))
    outro = _cfg_modelos(tmp_path / "p2")
    assert outro.embedding.model_cache_dir == str(tmp_path / "do-ambiente")
    assert models_dir(load_config(tmp_path / "p2")) == tmp_path / "do-ambiente"


def test_models_dir_vazio_na_configuracao_volta_para_o_cache_do_projeto(tmp_path) -> None:
    from ragx.embeddings import legacy_models_dir, models_dir

    cfg = _cfg_modelos(tmp_path, 'model_cache_dir = ""\n')
    assert models_dir(cfg) == legacy_models_dir(cfg)


def test_doctor_informa_o_cache_de_modelos_sem_mudar_o_veredito(tmp_path) -> None:
    from ragx.cli.commands.doctor import _cache_de_modelos
    from ragx.embeddings import legacy_models_dir

    linhas: list[tuple] = []

    def row(rotulo, valor, ok, dicas=None):
        linhas.append((rotulo, valor, ok, dicas or []))
        return ok

    cfg = _cfg_modelos(tmp_path)
    _cache_de_modelos(cfg, row)  # fastembed, sem cache legado: aponta a pasta do usuário
    assert linhas[-1][0] == "Cache de modelos" and "compartilhado" in linhas[-1][1] and linhas[-1][2] is True

    (legacy_models_dir(cfg) / "models--x").mkdir(parents=True)
    (legacy_models_dir(cfg) / "models--x" / "m.onnx").write_bytes(b"x" * 2048)
    _cache_de_modelos(cfg, row)  # com cache legado: tamanho e como migrar
    _rotulo, valor, ok, dicas = linhas[-1]
    assert ok is True and "em uso" in valor and any("apague essa pasta" in d for d in dicas)

    # outro provider e nenhum cache legado: nada a dizer
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\n', encoding="utf-8")
    import shutil

    shutil.rmtree(legacy_models_dir(cfg))
    from ragx.config import load_config

    antes = len(linhas)
    _cache_de_modelos(load_config(tmp_path), row)
    assert len(linhas) == antes


# ── prefixos declarados no fastembed (RAGX-0104) ────────────────────────
class _TextEmbeddingEco:
    """Registra o que o modelo recebeu e devolve um vetor que depende do texto."""

    recebidos: ClassVar[list[list[str]]] = []

    def __init__(self, **kwargs) -> None:
        pass

    def embed(self, textos, batch_size=32):
        import numpy as np

        _TextEmbeddingEco.recebidos.append(list(textos))
        for t in textos:
            v = np.zeros(8, dtype=np.float32)
            v[sum(map(ord, t)) % 8] = 1.0
            yield v


@pytest.fixture
def fastembed_eco(monkeypatch):
    import sys
    import types

    _TextEmbeddingEco.recebidos = []
    modulo = types.ModuleType("fastembed")
    modulo.TextEmbedding = _TextEmbeddingEco  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", modulo)
    return _TextEmbeddingEco


@pytest.mark.parametrize(
    ("modelo", "consulta", "documento"),
    [
        ("intfloat/multilingual-e5-large", "query: ", "passage: "),
        ("nomic-ai/nomic-embed-text-v1.5", "search_query: ", "search_document: "),
    ],
)
def test_consulta_e_documento_levam_prefixos_diferentes(fastembed_eco, modelo, consulta, documento) -> None:
    from ragx.embeddings.fastembed_provider import FastEmbedEmbedder

    e = FastEmbedEmbedder(model=modelo, dim=8)
    q = e.embed_query("texto igual")
    assert fastembed_eco.recebidos[-1] == [consulta + "texto igual"]
    d = e.embed_documents(["texto igual"])
    assert fastembed_eco.recebidos[-1] == [documento + "texto igual"]
    # o MESMO texto vira vetores diferentes conforme o lado
    assert not (q == d[0]).all()


def test_modelo_sem_prefixo_declarado_roda_sem_prefixo_e_com_o_id_de_sempre(fastembed_eco) -> None:
    from ragx.embeddings.fastembed_provider import DEFAULT_MODEL, FastEmbedEmbedder, prefixes_for

    assert prefixes_for(DEFAULT_MODEL) == ("", "")
    e = FastEmbedEmbedder(model=DEFAULT_MODEL, dim=8)
    e.embed_query("a")
    assert fastembed_eco.recebidos[-1] == ["a"]
    e.embed_documents(["b"])
    assert fastembed_eco.recebidos[-1] == ["b"]
    assert e.id == f"fastembed:{DEFAULT_MODEL}"  # os índices existentes continuam válidos


def test_o_mapa_e_declarado_nao_adivinhado_pelo_nome(fastembed_eco) -> None:
    """Um modelo com "e5" no nome mas fora do mapa NÃO ganha prefixo por heurística."""
    from ragx.embeddings.fastembed_provider import FastEmbedEmbedder, prefixes_for

    assert prefixes_for("acme/meu-e5-proprio") == ("", "")
    FastEmbedEmbedder(model="acme/meu-e5-proprio", dim=8).embed_query("x")
    assert fastembed_eco.recebidos[-1] == ["x"]


def test_o_prefixo_entra_no_id_e_trocar_o_mapa_troca_o_id(fastembed_eco, monkeypatch) -> None:
    from ragx.embeddings import fastembed_provider as fp

    modelo = "intfloat/multilingual-e5-large"
    antes = fp.model_id(modelo)
    assert antes.startswith(f"fastembed:{modelo}#p") and antes != f"fastembed:{modelo}"
    assert fp.FastEmbedEmbedder(model=modelo, dim=8).id == antes
    monkeypatch.setitem(fp.PREFIXES, modelo, ("consulta: ", "documento: "))
    depois = fp.model_id(modelo)
    assert depois != antes  # outro texto embutido = vetores incompatíveis = outro id (cache e vetores invalidados)


def test_embedder_id_de_modelo_com_prefixo_nao_diverge_do_construido(fastembed_eco) -> None:
    import tempfile
    from pathlib import Path

    from ragx.config import load_config
    from ragx.embeddings import build_embedder, embedder_id, reset_embedder_cache

    raiz = Path(tempfile.mkdtemp())
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "fastembed"\n'
        'model = "nomic-ai/nomic-embed-text-v1.5"\ndim = 8\n',
        encoding="utf-8",
    )
    cfg = load_config(raiz)
    reset_embedder_cache()
    try:
        assert embedder_id(cfg) == build_embedder(cfg).id and "#p" in embedder_id(cfg)
    finally:
        reset_embedder_cache()

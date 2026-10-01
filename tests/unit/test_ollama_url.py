"""`localhost` vira `127.0.0.1` em toda requisição ao Ollama.

No Windows, `localhost` resolve para `::1` antes de `127.0.0.1` e o Ollama
escuta só em IPv4: cada requisição esperava ~2 s até cair no endereço certo.
Medido nesta máquina: 2,04-2,11 s com `localhost`, 3-17 ms com `127.0.0.1`.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0132-*.md`.
"""

from __future__ import annotations

import json

import pytest

from ragx.config import Config, EmbeddingCfg, load_config, resolve_base_url
from ragx.embeddings import build_embedder, reset_embedder_cache
from ragx.embeddings.ollama import OllamaEmbedder

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("http://localhost:11434", "http://127.0.0.1:11434"),
        ("HTTP://LOCALHOST:11434/", "http://127.0.0.1:11434/"),
        ("localhost:11434", "http://127.0.0.1:11434"),
        ("http://localhost", "http://127.0.0.1"),
        ("http://u:p@localhost:1/x?y=1", "http://u:p@127.0.0.1:1/x?y=1"),
        # outro host: a escolha da pessoa é respeitada
        ("http://localhost.exemplo.com", "http://localhost.exemplo.com"),
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
        ("http://host:11434/api", "http://host:11434/api"),
        ("http://minha-rede.local:11434", "http://minha-rede.local:11434"),
        ("", ""),
    ],
)
def test_resolve_base_url(entrada: str, esperado: str) -> None:
    assert resolve_base_url(entrada) == esperado


def test_padrao_da_configuracao_ja_e_ipv4() -> None:
    assert EmbeddingCfg().base_url == "http://127.0.0.1:11434"


def test_configuracao_antiga_com_localhost_ganha_a_correcao() -> None:
    assert EmbeddingCfg(base_url="http://localhost:11434").base_url == "http://127.0.0.1:11434"


def test_ipv6_explicito_continua_valendo() -> None:
    assert EmbeddingCfg(base_url="http://[::1]:11434").base_url == "http://[::1]:11434"


def test_embedder_resolve_localhost() -> None:
    emb = OllamaEmbedder(base_url="http://localhost:11434/")
    assert emb.base_url == "http://127.0.0.1:11434"


def test_requisicoes_do_embedder_nao_usam_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    class Resp:
        def __init__(self, corpo: bytes) -> None:
            self._corpo = corpo

        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def read(self) -> bytes:
            return self._corpo

    def fake(req: object, timeout: float = 0) -> Resp:
        url = req if isinstance(req, str) else req.full_url  # type: ignore[attr-defined]
        urls.append(url)
        if url.endswith("/api/tags"):
            return Resp(json.dumps({"models": [{"name": "nomic-embed-text"}]}).encode())
        return Resp(json.dumps({"embeddings": [[0.1, 0.2, 0.3]]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    emb = OllamaEmbedder(base_url="http://localhost:11434", dim=3)
    assert emb.available()
    emb.embed_query("oi")
    assert urls
    assert all("localhost" not in u for u in urls), urls


def test_variavel_ragx_e_ollama_host_passam_pelo_normalizador(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")
    monkeypatch.setenv("OLLAMA_HOST", "localhost:11434")
    cfg = load_config(tmp_path)
    assert cfg.embedding.base_url == "http://127.0.0.1:11434"

    monkeypatch.delenv("OLLAMA_HOST")
    monkeypatch.setenv("RAGX_EMBEDDING_BASE_URL", "http://localhost:9999")
    cfg = load_config(tmp_path)
    assert cfg.embedding.base_url == "http://127.0.0.1:9999"


def test_cache_de_embedder_junta_as_duas_grafias(tmp_path) -> None:
    reset_embedder_cache()

    def _cfg(url: str) -> Config:
        cfg = Config()
        cfg.embedding = EmbeddingCfg(provider="ollama", base_url=url, dim=8)
        return cfg

    try:
        a = build_embedder(_cfg("http://localhost:11434"))
        b = build_embedder(_cfg("http://127.0.0.1:11434"))
        assert a is b
    finally:
        reset_embedder_cache()

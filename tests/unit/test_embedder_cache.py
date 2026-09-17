"""O embedder é construído uma vez por processo — e isso não muda resultado.

`build_embedder` era chamado a cada busca semântica, e de novo dentro do
`build_context`. Construir o `FastEmbedEmbedder` carrega um modelo ONNX e custa
2,5–3,6 s; embutir a consulta com ele pronto custa ~10 ms. Praticamente toda a
latência da busca semântica era carregar o modelo de novo.

Estes testes protegem as duas metades do acordo: que a instância é reusada, e
que reusá-la não altera o que a busca devolve. A segunda metade importa porque
um embedder com estado sujo entre chamadas seria um bug muito pior que a
lentidão que o cache resolve.

Ver `task/fase-14-evolucao-do-rag/RAGX-0097-*.md`.
"""

from __future__ import annotations

import pytest

from ragx.config import Config, load_config
from ragx.embeddings import build_embedder, reset_embedder_cache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def cache_limpo():
    """Cada teste começa sem instância pendurada do anterior."""
    reset_embedder_cache()
    yield
    reset_embedder_cache()


def _cfg(tmp_path, **embedding) -> Config:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        "[embedding]\n"
        + "".join(
            f"{k} = {v!r}\n".replace("'", '"') for k, v in
            {"provider": "hashing", "dim": 64, **embedding}.items()
        ),
        encoding="utf-8",
    )
    return load_config(tmp_path)


def test_a_segunda_chamada_devolve_a_mesma_instancia(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    assert build_embedder(cfg) is build_embedder(cfg)


def test_config_equivalente_compartilha_a_instancia(tmp_path) -> None:
    """Dois `Config` carregados do mesmo projeto não constroem dois modelos."""
    cfg = _cfg(tmp_path)
    outro = load_config(tmp_path)
    assert build_embedder(cfg) is build_embedder(outro)


def test_modelo_diferente_nao_compartilha(tmp_path) -> None:
    a = _cfg(tmp_path / "a", dim=64)
    b = _cfg(tmp_path / "b", dim=128)
    assert build_embedder(a) is not build_embedder(b)


def test_projetos_diferentes_nao_compartilham(tmp_path) -> None:
    """O fastembed guarda o modelo baixado sob `state_dir`; misturar dois
    projetos faria um usar o diretório do outro."""
    a = _cfg(tmp_path / "p1")
    b = _cfg(tmp_path / "p2")
    assert build_embedder(a) is not build_embedder(b)


def test_reset_descarta(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    primeiro = build_embedder(cfg)
    reset_embedder_cache()
    assert build_embedder(cfg) is not primeiro


def test_o_cache_tem_teto(tmp_path) -> None:
    """Uma suíte que varre configurações não pode segurar N modelos na memória."""
    from ragx.embeddings import _CACHE, _MAX_CACHE

    for i in range(_MAX_CACHE + 3):
        build_embedder(_cfg(tmp_path / f"p{i}"))
    assert len(_CACHE) <= _MAX_CACHE


def test_reusar_o_embedder_nao_muda_o_vetor(tmp_path) -> None:
    """O acordo que torna o cache seguro: nenhum estado sujo entre chamadas."""
    cfg = _cfg(tmp_path)
    e = build_embedder(cfg)

    primeiro = e.embed_query("autenticacao via SSO")
    _ = e.embed_query("outra coisa completamente diferente")
    depois = e.embed_query("autenticacao via SSO")

    assert (primeiro == depois).all(), (
        "o mesmo texto produziu vetores diferentes na mesma instância — "
        "há estado sobrevivendo entre chamadas, e o cache é inseguro"
    )


def test_a_busca_devolve_os_mesmos_ids_em_chamadas_repetidas(tmp_path) -> None:
    """Contrato de ponta a ponta: cachear o embedder é ganho de tempo, não de
    resultado. Duas buscas iguais no mesmo processo devolvem a mesma ordem."""
    from ragx.indexing.pipeline import index_project
    from ragx.search.service import search

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text(
        'class AuthService:\n    """Autentica via SSO."""\n\n'
        "    def login(self, c):\n        return c\n",
        encoding="utf-8",
    )
    (tmp_path / "doc.md").write_text(
        "# Autenticacao\n\nO AuthService valida o token no provedor SSO.\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    index_project(cfg)

    def ids(modo: str) -> list[str]:
        return [r.chunk_id for r in search(cfg, "autenticacao SSO", mode=modo, limit=5).results]

    for modo in ("keyword", "semantic", "hybrid"):
        assert ids(modo) == ids(modo), f"resultado instável em {modo}"

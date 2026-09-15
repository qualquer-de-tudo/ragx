from __future__ import annotations

import pytest

from ragx.search.hybrid import matched_by, rrf
from ragx.search.keyword import prepare_query, split_identifier
from ragx.search.ranking import diversify, looks_like_identifier, looks_like_question

pytestmark = pytest.mark.unit


# ── RRF ─────────────────────────────────────────────────────────────────
def test_rrf_premia_quem_aparece_nos_dois_motores() -> None:
    s = rrf({"semantic": ["a", "b", "c"], "keyword": ["c", "a", "z"]})
    assert s["a"] > s["b"] and s["a"] > s["z"]


def test_rrf_respeita_pesos() -> None:
    forte = rrf({"semantic": ["a"], "keyword": ["b"]}, {"semantic": 2.0, "keyword": 0.5})
    assert forte["a"] > forte["b"]


def test_rrf_usa_posicao_nao_score() -> None:
    """É o que dispensa calibrar cosseno contra BM25."""
    s = rrf({"x": ["primeiro", "segundo"]})
    assert s["primeiro"] > s["segundo"]


def test_matched_by_registra_origem() -> None:
    m = matched_by({"semantic": ["a"], "keyword": ["a", "b"]})
    assert m["a"] == ("keyword", "semantic") and m["b"] == ("keyword",)


# ── Preparação de query ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "token,esperado",
    [
        ("AuthService", ["auth", "service"]),
        ("auth_service", ["auth", "service"]),
        ("HTTPServer", ["http", "server"]),
        ("getUserById", ["get", "user", "by", "id"]),
    ],
)
def test_split_identifier(token: str, esperado: list[str]) -> None:
    assert split_identifier(token) == esperado


def test_query_encontra_camelcase_por_palavras() -> None:
    q = prepare_query("auth service")
    assert '"auth"' in q and '"service"' in q


def test_camelcase_gera_termos_adicionais() -> None:
    q = prepare_query("AuthService")
    assert '"auth"' in q and '"service"' in q


@pytest.mark.parametrize(
    "perigoso",
    ['" OR "', "NEAR(a b)", "a AND NOT b", 'x" OR chunks_fts MATCH "y', "*", "-", "()"],
)
def test_operadores_fts_do_usuario_sao_escapados(perigoso: str) -> None:
    """Input do usuário nunca é interpretado como sintaxe sem --raw."""
    q = prepare_query(perigoso)
    assert "MATCH" not in q
    assert q.count('"') % 2 == 0, f"aspas desbalanceadas: {q}"


def test_raw_preserva_a_sintaxe() -> None:
    assert prepare_query("a NEAR b", raw=True) == "a NEAR b"


def test_query_vazia_nao_quebra() -> None:
    assert prepare_query("   ") == '""'


def test_acentuacao_preservada_nos_termos() -> None:
    assert "autenticação" in prepare_query("autenticação")


# ── Ranking ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", ["como funciona auth?", "o que é SSO", "por que expira"])
def test_detecta_pergunta(q: str) -> None:
    assert looks_like_question(q)


@pytest.mark.parametrize("q", ["AuthService", "Auth::login", "get_user()"])
def test_detecta_identificador(q: str) -> None:
    assert looks_like_identifier(q)


def test_diversidade_limita_por_documento() -> None:
    from ragx.core.models import ChunkKind, SearchResult

    rs = [
        SearchResult(
            chunk_id=f"c{i}", document_path="mesmo.py", kind=ChunkKind.METHOD,
            start_line=i, end_line=i, score=1.0 - i / 100, content="x",
        )
        for i in range(8)
    ]
    out = diversify(rs, max_per_document=3)
    assert len(out) == 8, "excedentes descem, não somem"
    assert all(r.document_path == "mesmo.py" for r in out[:3])

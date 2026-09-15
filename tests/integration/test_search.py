from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.search.service import SearchFilters, search

pytestmark = pytest.mark.integration

AUTH_PY = '''class AuthService:
    """Servico de autenticacao corporativa."""

    def login(self, credentials):
        """Valida o token contra o provedor SSO e cria a sessao."""
        session = self.sso.validate(credentials)
        self.redis.setex(session.id, 1800, session.payload)
        return session
'''

AUTH_MD = """# Autenticacao

## Fluxo SSO

O sistema delega a verificacao de identidade ao provedor corporativo.
Depois de validado o usuario recebe uma sessao guardada no Redis.
"""

PAY_MD = """# Pagamentos

O servico de cobranca integra com o gateway externo e registra a transacao.
"""


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\n'
        'provider = "hashing"\ndim = 256\nversioned_dim = 128\n',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "AuthService.py").write_text(AUTH_PY, encoding="utf-8")
    (tmp_path / "docs" / "auth.md").write_text(AUTH_MD, encoding="utf-8")
    (tmp_path / "docs" / "pagamentos.md").write_text(PAY_MD, encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    return tmp_path


def test_keyword_acha_simbolo_exato_em_primeiro(proj: Path) -> None:
    out = search(load_config(proj), "AuthService", mode="keyword", limit=5)
    assert out.results
    assert "AuthService" in (out.results[0].symbol or "")


def test_todo_resultado_tem_fonte_score_e_metadata(proj: Path) -> None:
    out = search(load_config(proj), "sessao", limit=5)
    assert out.results
    for r in out.results:
        assert r.document_path and r.chunk_id and r.content
        assert r.start_line > 0 and r.end_line >= r.start_line
        assert r.metadata.get("lang") is not None
        assert r.project == "current"


def test_hibrido_combina_os_dois_motores(proj: Path) -> None:
    out = search(load_config(proj), "sessao redis", mode="hybrid", limit=10)
    fontes = {s for r in out.results for s in r.matched_by}
    assert "keyword" in fontes and "semantic" in fontes


def test_embeddings_foram_gerados(proj: Path) -> None:
    out = search(load_config(proj), "autenticacao", mode="semantic", limit=5)
    assert out.degraded is None, out.degraded
    assert out.results


def test_filtro_por_kind_aplica_antes_do_topk(proj: Path) -> None:
    out = search(load_config(proj), "sessao", limit=5, filters=SearchFilters(kind="method"))
    assert out.results, "filtro restritivo não pode devolver lista vazia havendo match"
    assert all(r.kind.value == "method" for r in out.results)


def test_filtro_por_lang(proj: Path) -> None:
    out = search(load_config(proj), "autenticacao", limit=5, filters=SearchFilters(lang="markdown"))
    assert out.results and all(r.metadata["lang"] == "markdown" for r in out.results)


def test_filtro_por_path(proj: Path) -> None:
    out = search(load_config(proj), "sessao", limit=5, filters=SearchFilters(path_glob="docs/*"))
    assert out.results and all(r.document_path.startswith("docs/") for r in out.results)


def test_filtro_sem_resultado_nao_quebra(proj: Path) -> None:
    out = search(load_config(proj), "sessao", filters=SearchFilters(lang="cobol"))
    assert out.results == []


def test_keyword_sem_match_devolve_vazio(proj: Path) -> None:
    assert search(load_config(proj), "zzzz_inexistente_qqq", mode="keyword").results == []


def test_semantico_sempre_devolve_vizinhos(proj: Path) -> None:
    """Não existe "sem match" em espaço de cosseno sem limiar: o semântico
    devolve os vizinhos mais próximos, por piores que sejam. Quem corta é
    --min-score."""
    cfg = load_config(proj)
    out = search(cfg, "zzzz_inexistente_qqq", mode="semantic", limit=5)
    assert out.results, "semântico devolve vizinhos mesmo sem relevância"
    alto = search(
        cfg, "zzzz_inexistente_qqq", mode="semantic", limit=5,
        filters=SearchFilters(min_score=0.9),
    )
    assert alto.results == [], "--min-score precisa cortar o ruído"


def test_query_maliciosa_nao_quebra(proj: Path) -> None:
    cfg = load_config(proj)
    for q in ['" OR "', "NEAR(", "*", "a AND NOT", "'; DROP TABLE chunks; --"]:
        search(cfg, q, limit=3)  # não pode lançar


def test_diversidade_no_topo(proj: Path) -> None:
    out = search(load_config(proj), "sessao autenticacao redis", limit=10)
    topo = out.results[:3]
    por_doc: dict[str, int] = {}
    for r in topo:
        por_doc[r.document_path] = por_doc.get(r.document_path, 0) + 1
    assert max(por_doc.values(), default=0) <= 3


def test_timings_reportados(proj: Path) -> None:
    out = search(load_config(proj), "sessao")
    assert {"keyword", "semantic", "fusion"} <= set(out.timings_ms)


def test_busca_sem_vetores_locais_ainda_funciona(proj: Path) -> None:
    """Simula um git clone: só os vetores int8 versionados existem."""
    import sqlite3

    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("UPDATE embeddings SET vector = NULL")
    conn.commit()
    conn.close()

    out = search(cfg, "autenticacao", mode="semantic", limit=5)
    assert out.degraded is None
    assert out.results, "o estágio grosseiro int8 precisa bastar sozinho"


def test_embedder_fora_do_ar_degrada_para_keyword(proj: Path) -> None:
    cfg = load_config(proj)
    cfg.embedding.provider = "ollama"
    cfg.embedding.base_url = "http://127.0.0.1:9"  # porta fechada
    cfg.embedding.timeout_s = 1
    out = search(cfg, "autenticacao", mode="hybrid", limit=5)
    assert out.degraded is not None
    assert out.results, "keyword deve continuar respondendo"

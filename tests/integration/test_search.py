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


# ── RAGX-0136: a busca usa o modelo CONFIGURADO e avisa quando o índice é parcial ──
def _semantic_ids(out) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.chunk_id for r in out.results if "semantic" in r.matched_by]


def test_modelo_configurado_com_dimensao_diferente_nao_estoura(proj: Path) -> None:
    """Índice 128d (hashing:256), configuração pede hashing dim=64: era
    `ValueError: matmul` fora do `try` que só cobria o embedder."""
    cfg = load_config(proj)
    cfg.embedding.dim = 64
    cfg.embedding.versioned_dim = 32
    out = search(cfg, "autenticacao sso", mode="hybrid", limit=5)
    assert out.degraded is not None
    assert "hashing:256" in out.degraded and "hashing:64" in out.degraded
    assert out.results, "a busca por palavra-chave continua respondendo"
    assert not _semantic_ids(out)


def test_dois_modelos_com_a_mesma_dimensao_usa_o_configurado(proj: Path) -> None:
    import sqlite3

    import numpy as np

    cfg = load_config(proj)
    antes = _semantic_ids(search(cfg, "autenticacao sso", mode="semantic", limit=5))
    assert antes

    conn = sqlite3.connect(cfg.db_path)
    try:
        conn.execute(
            "INSERT INTO embedding_models(id, dim, versioned_dim, quant, normalized, created_at) "
            "VALUES ('outro:modelo', 256, 128, 'int8', 1, '2999-01-01T00:00:00Z')"
        )
        rng = np.random.default_rng(7)
        for (cid,) in conn.execute("SELECT chunk_id FROM embeddings").fetchall():
            v = rng.standard_normal(256).astype(np.float32)
            v /= np.linalg.norm(v)
            q = np.clip(np.round((v[:128] - v[:128].min()) / ((v[:128].max() - v[:128].min()) / 255)),
                        0, 255).astype(np.uint8)
            conn.execute(
                "INSERT INTO embeddings(chunk_id, model_id, vector, vector_q, q_scale, q_offset, created_at) "
                "VALUES (?, 'outro:modelo', ?, ?, ?, ?, '2999-01-01T00:00:00Z')",
                (cid, v.tobytes(), q.tobytes(), float((v[:128].max() - v[:128].min()) / 255),
                 float(v[:128].min())),
            )
        conn.commit()
    finally:
        conn.close()
    depois = _semantic_ids(search(cfg, "autenticacao sso", mode="semantic", limit=5))
    assert depois == antes, "a busca leu o modelo mais recente do banco, não o configurado"


def test_modelo_configurado_sem_vetores_cita_os_dois_e_nao_usa_semantico(proj: Path) -> None:
    cfg = load_config(proj)
    cfg.embedding.provider = "ollama"
    cfg.embedding.model = "outro-modelo"
    cfg.embedding.base_url = "http://127.0.0.1:9"
    out = search(cfg, "autenticacao", mode="hybrid", limit=5)
    assert out.degraded is not None
    assert "ollama:outro-modelo" in out.degraded and "hashing:256" in out.degraded
    assert "embed-only" in out.degraded
    assert not _semantic_ids(out)


def test_indice_sem_vetor_nenhum_mantem_a_mensagem_atual(proj: Path) -> None:
    import sqlite3

    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("DELETE FROM embeddings")
    conn.commit()
    conn.close()
    out = search(cfg, "autenticacao", mode="hybrid", limit=5)
    assert out.degraded and "sem embeddings" in out.degraded


def test_indice_parcial_avisa_e_ainda_busca_no_semantico(proj: Path) -> None:
    import sqlite3

    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.execute(
        "DELETE FROM embeddings WHERE chunk_id IN "
        "(SELECT chunk_id FROM embeddings ORDER BY rowid LIMIT ?)", (total // 2,)
    )
    conn.commit()
    restantes = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    conn.close()
    out = search(cfg, "autenticacao sso", mode="hybrid", limit=5)
    assert out.degraded is None, "o semântico RODOU: não é degradação"
    assert out.partial is not None
    assert f"{restantes} de {total}" in out.partial
    assert _semantic_ids(out) or any(r.matched_by for r in out.results)


def test_indice_completo_nao_tem_degraded_nem_partial(proj: Path) -> None:
    out = search(load_config(proj), "autenticacao sso", mode="hybrid", limit=5)
    assert out.degraded is None and out.partial is None

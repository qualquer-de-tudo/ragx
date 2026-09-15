from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import graph_search, rebuild
from ragx.graph.store import GraphStore
from ragx.graph.traversal import TraversalLimits, expand
from ragx.indexing.pipeline import index_project
from ragx.storage.db import open_db

pytestmark = pytest.mark.integration

AUTH = '''import redis


class AuthService:
    """Autentica usuarios via SSO corporativo."""

    def login(self, credentials):
        """Valida o token no provedor e cria a sessao."""
        return self.sso.validate(credentials)

    def logout(self, session_id):
        """Encerra a sessao e limpa o cache do usuario."""
        self.cache.delete(session_id)
        self.audit.record("logout", session_id)
        return True
'''

CONTROLLER = '''from auth import AuthService


class LoginController:
    """Recebe a requisicao HTTP de login."""

    def store(self, request):
        service = AuthService()
        return service.login(request.body)
'''

ROUTES = """from fastapi import APIRouter

router = APIRouter()


@router.post("/api/login")
def login_route(payload):
    return payload


@router.get("/api/users/{user_id}")
def get_user(user_id):
    return user_id
"""

SCHEMA = """CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY
);
"""

DOC = """# Autenticacao

## Fluxo

O AuthService valida o token contra o provedor SSO e guarda a sessao.
O LoginController apenas delega para o servico.
"""

PYPROJECT = """[project]
name = "demo"
dependencies = ["fastapi", "redis", "pydantic"]
"""


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "auth.py").write_text(AUTH, encoding="utf-8")
    (tmp_path / "controller.py").write_text(CONTROLLER, encoding="utf-8")
    (tmp_path / "routes.py").write_text(ROUTES, encoding="utf-8")
    (tmp_path / "schema.sql").write_text(SCHEMA, encoding="utf-8")
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    return tmp_path


def _entities(proj: Path, etype: str | None = None) -> list[dict]:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        return GraphStore(conn).list_entities(etype, limit=500)


# ── Camada 1: estrutural ────────────────────────────────────────────────
def test_hierarquia_arquivo_classe_metodo(proj: Path) -> None:
    nomes = {e["name"] for e in _entities(proj)}
    assert {"AuthService", "login", "logout", "LoginController", "auth.py"} <= nomes


def test_metodo_pertence_a_classe(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        cls = store.find("AuthService")[0]
        edges = store.neighbors([cls["id"]], ("contains",))
    filhos = {e["other_name"] for e in edges if e["direction"] == "out"}
    assert {"login", "logout"} <= filhos


def test_metodo_trivial_e_fundido_e_some_do_grafo(tmp_path: Path) -> None:
    """Trade-off documentado da Fase 1: método abaixo de `min_tokens` é fundido
    com o vizinho, então não vira entidade própria. O conteúdo continua
    recuperável pelo chunk do irmão — o que se perde é a granularidade do grafo.
    """
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "tiny.py").write_text(
        "class Config:\n"
        "    def get_a(self):\n        return 1\n\n"
        "    def get_b(self):\n        return 2\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        nomes = {e["name"] for e in GraphStore(conn).list_entities(limit=100)}
        conteudo = " ".join(
            r[0] for r in conn.execute("SELECT content FROM chunks").fetchall()
        )
    assert "get_a" in nomes
    assert "get_b" not in nomes, "fusão esperada não aconteceu"
    assert "get_b" in conteudo, "o conteúdo do método fundido precisa continuar indexado"


def test_camada_1_roda_sem_nenhum_llm(proj: Path) -> None:
    cfg = load_config(proj)
    r = rebuild(cfg, layers=(1,))
    assert r.stats.entities > 0 and r.stats.relations > 0


# ── Camada 2: referencial ───────────────────────────────────────────────
def test_tecnologia_por_dependencia_declarada_tem_confianca_maxima(proj: Path) -> None:
    techs = {e["name"]: e for e in _entities(proj, "technology")}
    assert "FastAPI" in techs and "Redis" in techs
    assert techs["FastAPI"]["confidence"] >= 0.9


def test_endpoints_normalizados(proj: Path) -> None:
    nomes = {e["name"] for e in _entities(proj, "endpoint")}
    assert "POST /api/login" in nomes
    assert "GET /api/users/{}" in nomes, f"rota não normalizada: {nomes}"


def test_tabelas_extraidas_do_sql(proj: Path) -> None:
    nomes = {e["name"] for e in _entities(proj, "table")}
    assert {"users", "sessions"} <= nomes


def test_documentacao_liga_ao_codigo(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        cls = store.find("AuthService")[0]
        edges = store.neighbors([cls["id"]], ("documented_by",))
    docs = {e["other_name"] for e in edges}
    assert "doc.md" in docs


def test_chamada_entre_arquivos_vira_calls(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        edges = conn.execute(
            """SELECT s.name AS src, d.name AS dst FROM relations r
               JOIN entities s ON s.id = r.src_id
               JOIN entities d ON d.id = r.dst_id
               WHERE r.type = 'calls'"""
        ).fetchall()
    pares = {(e["src"], e["dst"]) for e in edges}
    assert any(dst == "AuthService" for _src, dst in pares), pares


def test_prosa_menciona_nao_chama(proj: Path) -> None:
    """Documentação que cita AuthService.login() MENCIONA; só código CHAMA."""
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        rows = conn.execute(
            """SELECT r.type FROM relations r
               JOIN entities s ON s.id = r.src_id
               JOIN documents doc ON doc.id = s.document_id
               WHERE doc.doc_kind = 'doc' AND r.type = 'calls'"""
        ).fetchall()
    assert rows == []


def test_nao_inventa_no_para_entidade_inexistente(proj: Path) -> None:
    """Camada 2 só liga para entidade que já existe."""
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        orfas = conn.execute(
            """SELECT COUNT(*) FROM relations r
               WHERE r.src_id NOT IN (SELECT id FROM entities)
                  OR r.dst_id NOT IN (SELECT id FROM entities)"""
        ).fetchone()[0]
    assert orfas == 0


# ── Reconstrução ────────────────────────────────────────────────────────
def test_rebuild_e_idempotente(proj: Path) -> None:
    cfg = load_config(proj)
    a = rebuild(cfg).stats
    b = rebuild(cfg).stats
    assert (a.entities, a.relations) == (b.entities, b.relations)


def test_rebuild_nao_duplica(proj: Path) -> None:
    cfg = load_config(proj)
    rebuild(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        dup_e = conn.execute(
            "SELECT COUNT(*) FROM (SELECT type, qualified_name FROM entities "
            "GROUP BY type, qualified_name HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        dup_r = conn.execute(
            "SELECT COUNT(*) FROM (SELECT src_id, dst_id, type FROM relations "
            "GROUP BY src_id, dst_id, type HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    assert dup_e == 0 and dup_r == 0


def test_rebuild_preserva_camada_semantica(proj: Path) -> None:
    """A camada 3 custa dinheiro; rebuild das camadas 1-2 não pode apagá-la."""
    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO entities(id, type, name, qualified_name, confidence, source) "
        "VALUES ('sem1','concept','autenticacao','autenticacao',0.8,'semantic')"
    )
    conn.commit()
    conn.close()

    rebuild(cfg)

    conn = sqlite3.connect(cfg.db_path)
    n = conn.execute("SELECT COUNT(*) FROM entities WHERE source = 'semantic'").fetchone()[0]
    conn.close()
    assert n == 1


def test_documento_removido_leva_entidades_junto(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "controller.py").unlink()
    index_project(cfg)
    rebuild(cfg)
    nomes = {e["name"] for e in _entities(proj)}
    assert "LoginController" not in nomes


def test_rebuild_e_rapido(proj: Path) -> None:
    assert rebuild(load_config(proj)).duration_ms < 2000


# ── Travessia ───────────────────────────────────────────────────────────
def test_expansao_respeita_limites(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        seed = store.find("AuthService")[0]["id"]
        exp = expand(store, {seed: 1.0}, TraversalLimits(max_depth=2, max_nodes=5))
    assert len(exp.scores) <= 5


def test_decaimento_por_salto(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        seed = store.find("AuthService")[0]["id"]
        exp = expand(store, {seed: 1.0}, TraversalLimits(max_depth=2, decay=0.5))
    distantes = [exp.scores[e] for e, d in exp.depth.items() if d == 2]
    if distantes:
        assert max(distantes) < exp.scores[seed]


def test_expansao_vazia_nao_quebra(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        assert expand(GraphStore(conn), {}).scores == {}


# ── graph-search ────────────────────────────────────────────────────────
def test_graph_search_devolve_resultados(proj: Path) -> None:
    out = graph_search(load_config(proj), "autenticacao", limit=5)
    assert out.results and out.seeds > 0


def test_graph_search_marca_a_origem(proj: Path) -> None:
    out = graph_search(load_config(proj), "login", limit=10)
    assert all(r.metadata.get("via") for r in out.results)


def test_graph_search_alcanca_o_que_a_hibrida_sozinha_nao_alcanca(proj: Path) -> None:
    """O grafo precisa pagar o próprio custo."""
    from ragx.search.service import search

    cfg = load_config(proj)
    query = "LoginController"
    base = {r.document_path for r in search(cfg, query, limit=5).results}
    ampliado = {r.document_path for r in graph_search(cfg, query, limit=10).results}
    assert ampliado - base, f"grafo não acrescentou nada: {ampliado}"


def test_graph_search_e_rapido(proj: Path) -> None:
    out = graph_search(load_config(proj), "sessao", limit=5)
    assert out.timings_ms.get("graph", 0) < 300

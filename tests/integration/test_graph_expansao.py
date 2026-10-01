"""Expansão do grafo: semeadura pelo topo, filtros honrados, grau só dos visitados (RAGX-0145)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import graph_search, rebuild
from ragx.graph.store import GraphStore
from ragx.graph.traversal import TraversalLimits, expand
from ragx.indexing.pipeline import index_project
from ragx.search.service import SearchFilters, _filter_mask, filter_chunk_ids
from ragx.storage.db import open_db

pytestmark = pytest.mark.integration

N_MODULOS = 14


def _modulo(i: int) -> str:
    anterior = f"from m{i - 1} import Servico{i - 1}\n\n" if i else ""
    chamada = f"        return Servico{i - 1}().rodar(x)\n" if i else "        return x\n"
    return (
        f"{anterior}class Servico{i}:\n"
        f'    """Servico numero {i} de autenticacao de usuarios."""\n\n'
        f"    def rodar(self, x):\n"
        f'        """Autentica o usuario no modulo {i}."""\n'
        f"{chamada}"
    )


@pytest.fixture(scope="module")
def proj(tmp_path_factory: pytest.TempPathFactory) -> Path:
    raiz = tmp_path_factory.mktemp("grafo")
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (raiz / "src").mkdir()
    (raiz / "docs").mkdir()
    for i in range(N_MODULOS):
        (raiz / "src" / f"m{i}.py").write_text(_modulo(i), encoding="utf-8")
    (raiz / "docs" / "guia.md").write_text(
        "# Guia\n\n## Autenticacao\n\nO Servico3 e o Servico4 autenticam usuarios.\n", encoding="utf-8"
    )
    cfg = load_config(raiz)
    index_project(cfg)
    rebuild(cfg)
    return raiz


# ── semeadura ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("k", [2, 5])
def test_sementes_ficam_perto_de_seed_top_k_e_a_busca_anda(proj: Path, k: int) -> None:
    cfg = load_config(proj)
    cfg.graph.seed_top_k = k
    out = graph_search(cfg, "autenticacao de usuarios", limit=25, depth=2)
    assert 0 < out.seeds <= 3 * k
    assert out.expansion.visited > out.seeds or len(out.expansion.scores) > out.seeds  # a BFS passou das sementes


def test_truncated_so_quando_os_expandidos_estouram_o_teto(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        todas = [r["id"] for r in conn.execute("SELECT id FROM entities ORDER BY id")]
        # 300 sementes (aqui, todas as entidades repetidas por rodízio não cabem: usa as que existem)
        sementes = dict.fromkeys(todas, 1.0)
        folgado = expand(store, sementes, TraversalLimits(max_depth=1, max_nodes=len(todas)))
        apertado = expand(store, {todas[0]: 1.0}, TraversalLimits(max_depth=2, max_nodes=1))
    assert folgado.truncated is False  # as sementes sozinhas NÃO estouram o teto
    assert apertado.truncated is True and len(apertado.scores) - 1 <= 1


def test_sementes_nao_contam_contra_max_nodes(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        sementes = {r["id"]: 1.0 for r in conn.execute("SELECT id FROM entities")}
        exp = expand(store, sementes, TraversalLimits(max_depth=1, max_nodes=2))
    assert exp.visited == len(sementes)  # todas foram visitadas, nenhuma interrompeu a BFS no nível 0


def test_resultado_deterministico_em_duas_execucoes(proj: Path) -> None:
    cfg = load_config(proj)
    a = [r.chunk_id for r in graph_search(cfg, "autenticacao", limit=25).results]
    b = [r.chunk_id for r in graph_search(cfg, "autenticacao", limit=25).results]
    assert a == b and a


# ── filtros ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "filtros",
    [
        SearchFilters(path_glob="docs/*"),
        SearchFilters(path_glob="src/m1*"),
        SearchFilters(lang="markdown"),
        SearchFilters(kind="doc"),
    ],
)
def test_filtros_valem_para_os_chunks_vindos_do_grafo(proj: Path, filtros: SearchFilters) -> None:
    cfg = load_config(proj)
    out = graph_search(cfg, "autenticacao de usuarios", limit=25, depth=2, filters=filtros)
    with open_db(cfg.db_path, read_only=True) as conn:
        permitidos = filter_chunk_ids(conn, [r.chunk_id for r in out.results], filtros)
    assert all(r.chunk_id in permitidos for r in out.results), "o grafo trouxe chunk fora do filtro"


def test_path_glob_nao_deixa_o_grafo_reintroduzir_arquivo_de_fora(proj: Path) -> None:
    cfg = load_config(proj)
    out = graph_search(cfg, "Servico5", limit=25, depth=2, filters=SearchFilters(path_glob="docs/*"))
    assert all(r.document_path.startswith("docs/") for r in out.results)


# ── filtro compartilhado ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "filtros",
    [
        SearchFilters(path_glob="src/*"),
        SearchFilters(path_glob="SRC/M1%"),  # `%` literal e maiúsculas: o LIKE ignora caixa em ASCII
        SearchFilters(path_glob="*guia*"),
        SearchFilters(lang="python", kind="code"),
        SearchFilters(),
    ],
)
def test_filter_chunk_ids_tem_a_mesma_semantica_de_filter_mask(proj: Path, filtros: SearchFilters) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM chunks ORDER BY id")]
        mascara = _filter_mask(conn, ids, filtros)
        esperado = set(ids) if mascara is None else {cid for cid, ok in zip(ids, mascara, strict=True) if ok}
        assert filter_chunk_ids(conn, ids, filtros) == esperado


def test_filter_chunk_ids_aguenta_mais_ids_que_o_limite_de_variaveis(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM chunks")]
        muitos = ids + [f"inexistente-{i}" for i in range(1500)]
        assert filter_chunk_ids(conn, muitos, SearchFilters(path_glob="src/*")) == filter_chunk_ids(
            conn, ids, SearchFilters(path_glob="src/*")
        )


# ── grau só dos visitados ───────────────────────────────────────────────
def test_degrees_for_e_igual_ao_recorte_de_degrees(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)
        todos = store.degrees()
        escolhidos = list(todos)[::3]
        assert store.degrees_for(escolhidos) == {i: todos[i] for i in escolhidos}
        assert store.degrees_for([]) == {}
        assert store.degrees_for(["nao-existe"]) == {"nao-existe": 0}


def test_degrees_for_conta_auto_relacao_uma_vez() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """CREATE TABLE entities (id TEXT PRIMARY KEY);
           CREATE TABLE relations (id TEXT PRIMARY KEY, src_id TEXT, dst_id TEXT, type TEXT,
                                   weight REAL, confidence REAL, source TEXT);
           INSERT INTO entities VALUES ('a'), ('b');
           INSERT INTO relations VALUES ('r1','a','a','calls',1,1,'x'), ('r2','a','b','calls',1,1,'x');"""
    )
    store = GraphStore(conn)
    esperado = {
        r["id"]: int(r["d"])
        for r in conn.execute(
            "SELECT id, (SELECT COUNT(*) FROM relations WHERE src_id = e.id OR dst_id = e.id) AS d FROM entities e"
        )
    }
    assert store.degrees_for(["a", "b"]) == esperado == {"a": 2, "b": 1}


def test_empate_de_peso_e_desempatado_por_other_id() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """CREATE TABLE entities (id TEXT PRIMARY KEY, type TEXT, name TEXT, qualified_name TEXT);
           CREATE TABLE relations (id TEXT PRIMARY KEY, src_id TEXT, dst_id TEXT, type TEXT,
                                   weight REAL, confidence REAL, source TEXT);
           INSERT INTO entities VALUES ('s','class','S','S'), ('z','class','Z','Z'), ('m','class','M','M'), ('b','class','B','B');
           INSERT INTO relations VALUES ('1','s','z','calls',1,1,'x'), ('2','s','m','calls',1,1,'x'), ('3','s','b','calls',1,1,'x');"""
    )
    exp = expand(GraphStore(conn), {"s": 1.0}, TraversalLimits(max_depth=1, max_fanout=2))
    # fanout 2 com pesos iguais: ficam `b` e `m` (ordem de id), nunca `z`
    assert set(exp.scores) == {"s", "b", "m"}


# ── o que o `--explain` mostra ──────────────────────────────────────────
def test_stats_e_explain_mostram_sementes_expandidos_truncado_e_origem(proj: Path) -> None:
    from ragx.context.engine import build_context
    from ragx.context.render import explain

    cfg = load_config(proj)
    pack = build_context(cfg, "autenticacao de usuarios", budget=1500, use_cache=False)
    for chave in ("graph_seeds", "graph_nodes", "graph_expanded", "graph_truncated", "graph_only"):
        assert chave in pack.stats, chave
    assert pack.stats["graph_expanded"] == pack.stats["graph_nodes"] - pack.stats["graph_seeds"]
    texto = explain(pack)
    assert "graph_seeds" in texto and "graph_only" in texto and "graph_truncated" in texto

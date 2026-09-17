"""Contrato do grafo: o que o servidor MANDA para quem desenha o grafo.

O par deste arquivo é `vscode-plugin/tests/unit/graph-contract.test.ts`, que
fixa o que o cliente ENTENDE. Separados, cada lado passa sozinho e o grafo
aparece vazio na tela; juntos, um renomeio de campo quebra o teste em vez de
quebrar a interface.

O bug que os dois existem para impedir: `get_entity` devolvia a relação só
como "o nó do outro lado" (`other`, `other_type`), sem dizer quem era origem e
quem era destino. A extensão procurava `target`/`dst`, não achava, e descartava
a relação em silêncio — grafo sem nenhuma aresta, sem erro em lugar nenhum.
"""

from __future__ import annotations

import sqlite3

import pytest

from ragx.graph.store import Entity, EntityType, GraphStore, Relation, RelationType
from ragx.graph.traversal import neighborhood

#: O contrato mínimo de uma relação. Remover qualquer um destes campos quebra
#: quem desenha o grafo; por isso a lista está escrita, e não inferida.
CAMPOS_DA_RELACAO = {
    "direction", "type", "src_id", "dst_id", "other_id", "other_name",
    "other_type", "other_qname", "weight", "confidence", "provenance", "depth",
}


@pytest.fixture
def store(tmp_path) -> GraphStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    sql = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "src/ragx/storage/migrations/0004_graph.sql"
    ).read_text(encoding="utf-8")
    conn.executescript(sql)
    return GraphStore(conn)


def _entidade(nome: str, tipo: EntityType = EntityType.CLASS, **kw) -> Entity:
    return Entity(type=tipo, name=nome, qualified_name=f"src/{nome.lower()}.py::{nome}", **kw)


def test_relacao_carrega_as_duas_pontas_da_aresta(store: GraphStore) -> None:
    """`A -> B` sai identificando A e B, não só "o outro"."""
    a, b = _entidade("A"), _entidade("B")
    store.upsert_entities([a, b])
    store.upsert_relations([Relation(a.id, b.id, RelationType.IMPORTS)])

    rels = neighborhood(store, a.id, depth=1)
    assert len(rels) == 1
    r = rels[0]
    assert r["src_id"] == a.id
    assert r["dst_id"] == b.id
    assert r["other_id"] == b.id
    assert r["direction"] == "out"


def test_a_relacao_tem_todos_os_campos_do_contrato(store: GraphStore) -> None:
    a, b = _entidade("A"), _entidade("B")
    store.upsert_entities([a, b])
    store.upsert_relations([Relation(a.id, b.id, RelationType.CALLS)])

    r = neighborhood(store, a.id, depth=1)[0]
    faltando = CAMPOS_DA_RELACAO - set(r)
    assert not faltando, (
        f"o contrato do grafo perdeu campo(s): {sorted(faltando)}. "
        f"Quem desenha o grafo depende deles."
    )


def test_confidence_e_provenance_chegam_sem_perda(store: GraphStore) -> None:
    """`structural` (extraído do AST) e `reference` (inferido) precisam ser
    distinguíveis de fora — é o que separa "A importa B" de "A talvez cite B"."""
    a, b, c = _entidade("A"), _entidade("B"), _entidade("C")
    store.upsert_entities([a, b, c])
    store.upsert_relations(
        [
            Relation(a.id, b.id, RelationType.IMPORTS, confidence=1.0, source="structural"),
            Relation(a.id, c.id, RelationType.MENTIONS, confidence=0.6, source="reference"),
        ]
    )

    por_destino = {r["dst_id"]: r for r in neighborhood(store, a.id, depth=1)}
    assert por_destino[b.id]["confidence"] == 1.0
    assert por_destino[b.id]["provenance"] == "structural"
    assert por_destino[c.id]["confidence"] == 0.6
    assert por_destino[c.id]["provenance"] == "reference"


def test_direcao_de_entrada_nao_inverte_a_aresta(store: GraphStore) -> None:
    """Perguntar por B não pode fazer `A -> B` virar `B -> A`."""
    a, b = _entidade("A"), _entidade("B")
    store.upsert_entities([a, b])
    store.upsert_relations([Relation(a.id, b.id, RelationType.IMPORTS)])

    r = neighborhood(store, b.id, depth=1)[0]
    assert r["direction"] == "in"
    assert r["src_id"] == a.id, "a aresta continua saindo de A"
    assert r["dst_id"] == b.id
    assert r["other_id"] == a.id, "o 'outro lado', visto de B, é A"


def test_auto_referencia_sobrevive(store: GraphStore) -> None:
    a = _entidade("A")
    store.upsert_entities([a])
    store.upsert_relations([Relation(a.id, a.id, RelationType.CALLS)])

    rels = neighborhood(store, a.id, depth=1)
    assert rels, "recursão é uma relação real e não pode sumir"
    assert rels[0]["src_id"] == rels[0]["dst_id"] == a.id


def test_tipos_diferentes_entre_os_mesmos_nos_coexistem(store: GraphStore) -> None:
    a, b = _entidade("A"), _entidade("B")
    store.upsert_entities([a, b])
    store.upsert_relations(
        [
            Relation(a.id, b.id, RelationType.IMPORTS),
            Relation(a.id, b.id, RelationType.CALLS),
        ]
    )

    tipos = {r["type"] for r in neighborhood(store, a.id, depth=1)}
    assert tipos == {"imports", "calls"}, "o id da relação inclui o tipo — as duas coexistem"


def test_grafo_vazio_devolve_lista_vazia(store: GraphStore) -> None:
    assert neighborhood(store, "id-que-nao-existe", depth=1) == []


def test_entidade_sem_relacao_nao_inventa_aresta(store: GraphStore) -> None:
    a = _entidade("A")
    store.upsert_entities([a])
    assert neighborhood(store, a.id, depth=1) == []


def test_grafo_grande_mantem_todas_as_arestas(store: GraphStore) -> None:
    a = _entidade("A")
    outros = [_entidade(f"N{i}") for i in range(300)]
    store.upsert_entities([a, *outros])
    store.upsert_relations([Relation(a.id, o.id, RelationType.USES) for o in outros])

    rels = neighborhood(store, a.id, depth=1, max_fanout=1000)
    assert len(rels) == 300
    assert len({r["dst_id"] for r in rels}) == 300


def test_mcp_get_entity_expoe_o_contrato_canonico(tmp_path, monkeypatch) -> None:
    """A casca MCP não pode achatar a aresta de volta para "só o outro lado"."""
    # Monta um projeto mínimo com grafo real.
    from ragx.config import load_config
    from ragx.mcp.server import KnowledgeAPI
    from ragx.storage.db import open_db

    (tmp_path / "ragx.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    cfg.state_dir.mkdir(parents=True, exist_ok=True)

    with open_db(cfg.db_path) as conn:
        st = GraphStore(conn)
        a, b = _entidade("Alpha"), _entidade("Beta")
        st.upsert_entities([a, b])
        st.upsert_relations(
            [Relation(a.id, b.id, RelationType.IMPORTS, confidence=0.75, source="reference")]
        )
        conn.commit()

    out = KnowledgeAPI(cfg).get_entity("Alpha", depth=1)
    assert out["ok"], out
    rel = out["data"]["relations"][0]

    # As duas leituras da mesma aresta, lado a lado.
    assert rel["src"] == a.id and rel["dst"] == b.id, "a aresta orientada"
    assert rel["other"] == "Beta" and rel["other_id"] == b.id, "o nó do outro lado"
    assert rel["confidence"] == 0.75
    assert rel["provenance"] == "reference"
    assert out["data"]["entity"]["provenance"] == "structural"

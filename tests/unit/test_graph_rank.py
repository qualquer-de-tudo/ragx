"""PageRank dos arquivos e o repo map (RAGX-0168), sobre grafos de brinquedo com resultado conhecido."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from ragx.graph import rank as rk
from ragx.storage.db import open_db

pytestmark = pytest.mark.unit


class Grafo:
    """Banco de verdade (migrações aplicadas) com documentos, entidades e relações inseridos à mão."""

    def __init__(self, tmp: Path) -> None:
        self.path = tmp / "k.db"
        self._cm = open_db(self.path)  # guardado: se o gerenciador for coletado, ele fecha a conexão
        self.conn = self._cm.__enter__()
        self.n = 0

    def doc(self, rel: str, kind: str = "code") -> str:
        self.conn.execute(
            "INSERT INTO documents (id, rel_path, lang, doc_kind, size_bytes, mtime_ns, content_hash, indexed_at, chunker_version) "
            "VALUES (?, ?, 'python', ?, 1, 1, ?, 'x', 'v')",
            (rel, rel, kind, rel),
        )
        return rel

    def ent(self, doc: str, name: str, tipo: str = "function") -> str:
        self.n += 1
        eid = f"e{self.n}"
        self.conn.execute(
            "INSERT INTO entities (id, type, name, qualified_name, document_id, confidence, source) VALUES (?,?,?,?,?,1.0,'structural')",
            (eid, tipo, name, f"{doc}::{name}{self.n}", doc),
        )
        return eid

    def rel(self, src: str, dst: str, tipo: str = "calls", peso: float = 1.0, conf: float = 1.0) -> None:
        self.n += 1
        self.conn.execute(
            "INSERT INTO relations (id, src_id, dst_id, type, weight, confidence, source) VALUES (?,?,?,?,?,?,'reference')",
            (f"r{self.n}", src, dst, tipo, peso, conf),
        )

    def rank(self) -> dict[str, float]:
        return rk.file_rank(self.conn)

    def close(self) -> None:
        self._cm.__exit__(None, None, None)


@pytest.fixture
def g(tmp_path: Path):
    grafo = Grafo(tmp_path)
    yield grafo
    grafo.close()


def test_o_arquivo_chamado_por_dois_ganha_do_que_chama(g: Grafo) -> None:
    a, b, c = g.doc("src/a.py"), g.doc("src/b.py"), g.doc("src/c.py")
    ea, eb, ec = g.ent(a, "servico_central"), g.ent(b, "usa_central"), g.ent(c, "tambem_usa")
    g.rel(eb, ea)
    g.rel(ec, ea)
    r = g.rank()
    assert r[a] > r[b] and r[a] > r[c] and r[b] == r[c]


def test_no_sem_saida_nao_vaza_massa(g: Grafo) -> None:
    a, b = g.doc("src/a.py"), g.doc("src/b.py")
    g.rel(g.ent(b, "chama_a"), g.ent(a, "folha"))  # `a` não chama ninguém
    r = g.rank()
    assert sum(r.values()) == pytest.approx(1.0, abs=1e-4)


def test_aresta_para_nome_ambiguo_e_ignorada(g: Grafo) -> None:
    a, b = g.doc("src/a.py"), g.doc("src/b.py")
    origem = g.ent(b, "chamador")
    alvos = [g.ent(g.doc(f"src/h{i}.py"), "get") for i in range(rk.AMBIGUOUS_NAME + 1)]  # nome genérico, em vários arquivos
    g.rel(origem, alvos[0])
    r = g.rank()
    assert r == {}  # a única aresta apontava para um nome ambíguo
    # com nome único a mesma aresta conta
    g.rel(origem, g.ent(a, "nome_unico"))
    assert set(g.rank()) == {a, b}


def test_prosa_e_estrutura_nao_pesam(g: Grafo) -> None:
    a, doc = g.doc("src/a.py"), g.doc("docs/x.md", kind="doc")
    ea, ed = g.ent(a, "alvo"), g.ent(doc, "texto", tipo="file")
    for tipo in ("documented_by", "mentions", "contains"):
        g.rel(ed, ea, tipo)
    assert g.rank() == {}


def test_aresta_dentro_do_mesmo_arquivo_nao_conta(g: Grafo) -> None:
    a = g.doc("src/a.py")
    g.rel(g.ent(a, "f"), g.ent(a, "g"))
    assert g.rank() == {}


def test_a_saida_e_deterministica_e_nao_depende_da_ordem_das_relacoes(tmp_path: Path) -> None:
    resultados = []
    for i, ordem in enumerate(itertools.islice(itertools.permutations(range(4)), 3)):
        (tmp_path / f"o{i}").mkdir()
        grafo = Grafo(tmp_path / f"o{i}")
        docs = [grafo.doc(f"src/m{k}.py") for k in range(4)]
        ents = [grafo.ent(d, f"funcao_{k}") for k, d in enumerate(docs)]
        arestas = [(1, 0), (2, 0), (3, 1), (0, 3)]
        for j in ordem:
            grafo.rel(ents[arestas[j][0]], ents[arestas[j][1]])
        resultados.append(grafo.rank())
        grafo.close()
    assert resultados[0] == resultados[1] == resultados[2]
    assert all(round(v, 6) == v for v in resultados[0].values())  # arredondado a 6 casas


def test_ranked_files_so_codigo_da_camada_knowledge_e_com_simbolos_de_maior_grau(g: Grafo) -> None:
    a, b, t, k, tk = g.doc("src/a.py"), g.doc("src/b.py"), g.doc("tests/test_a.py"), g.doc("knowledge/x.py"), g.doc("task/t.py")
    ea1, ea2, _ea3 = g.ent(a, "muito_usada"), g.ent(a, "pouco_usada"), g.ent(a, "_privada")
    for doc, nome in ((b, "u1"), (t, "u2"), (k, "u3"), (tk, "u4")):
        g.rel(g.ent(doc, nome), ea1)
    g.rel(g.ent(b, "u5"), ea2)
    entradas = rk.ranked_files(g.conn)
    caminhos = [e.path for e in entradas]
    assert caminhos[0] == "src/a.py"
    assert not any(p.startswith(("tests/", "knowledge/", "task/")) for p in caminhos)
    assert entradas[0].symbols == ("muito_usada", "pouco_usada")  # maior grau de entrada primeiro; `_privada` fora


def test_select_by_budget_respeita_tokens_e_arquivos() -> None:
    entradas = [rk.MapEntry(f"src/pacote_longo/modulo_{i}.py", 0.1, ("Classe", "funcao")) for i in range(50)]
    escolhidos = rk.select_by_budget(entradas, tokens=100)
    from ragx.tokens import count_tokens

    assert 0 < len(escolhidos) < 50
    assert sum(count_tokens(rk.format_line(e)) + 1 for e in escolhidos) <= 100
    assert len(rk.select_by_budget(entradas, tokens=10_000, files=7)) == 7


def test_grafo_vazio_devolve_vazio(g: Grafo) -> None:
    assert g.rank() == {} and rk.ranked_files(g.conn) == []

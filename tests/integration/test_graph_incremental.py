"""Grafo incremental por documento (RAGX-0151): `update_documents` tem de dar o MESMO grafo que o `rebuild`.

A referência de correção é o rebuild completo: depois de cada edição o grafo atualizado por documento é
comparado, linha a linha, com o de um `rebuild` rodado no mesmo banco. A exceção declarada é a das tecnologias
(`technology` e `uses`), que no caminho rápido só acrescentam e por isso podem ser superconjunto.
"""

from __future__ import annotations

import random
import shutil
import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import rebuild, update_documents
from ragx.indexing.pipeline import index_project
from ragx.storage.db import open_db

pytestmark = pytest.mark.integration

N_MODULOS = 6

_ENTIDADE = "id, type, name, qualified_name, document_id, chunk_id, summary, confidence, source"
_RELACAO = "id, src_id, dst_id, type, weight, confidence, source, evidence_chunk_id"


def _modulo(i: int, j: int) -> str:
    return f'''from mod{j} import Cls{j}


class Cls{i}:
    """Servico {i} do dominio, conversa com o servico {j}."""

    def run(self, x):
        """Executa o servico {i} e delega ao vizinho."""
        total = Cls{j}().run(x) + {i}
        for item in range({i} + 3):
            total += item * {i}
        return total

    def verificar_{i}(self, valor):
        """Valida o valor recebido pelo servico {i}."""
        if valor is None:
            raise ValueError("valor ausente no servico {i}")
        return Cls{j}().run(valor) > {i}


def func_{i}(x):
    """Funcao de entrada do modulo {i}."""
    resultado = Cls{i}().run(x)
    resultado += Cls{j}().run(x) * {i}
    return resultado
'''


ROTAS = '''from fastapi import APIRouter

router = APIRouter()


@router.post("/api/login")
def login_route(payload):
    """Recebe o login e delega ao Cls0."""
    return Cls0().run(payload)


@router.get("/api/users/{user_id}")
def get_user(user_id):
    """Busca o usuario pelo id."""
    return user_id
'''

SCHEMA = """CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY
);
"""

DOC = """# Servicos

## Fluxo

O Cls0 delega ao Cls1, que valida com func_2. O Cls3 e o Cls4 completam a cadeia.
"""

PYPROJECT = '[project]\nname = "demo"\ndependencies = ["fastapi", "redis"]\n'


def _montar(raiz: Path) -> None:
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (raiz / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    for i in range(N_MODULOS):
        (raiz / f"mod{i}.py").write_text(_modulo(i, (i + 1) % N_MODULOS), encoding="utf-8")
    (raiz / "rotas.py").write_text(ROTAS, encoding="utf-8")
    (raiz / "schema.sql").write_text(SCHEMA, encoding="utf-8")
    (raiz / "servicos.md").write_text(DOC, encoding="utf-8")


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Projeto já indexado e com grafo; cada teste trabalha numa cópia."""
    raiz = tmp_path_factory.mktemp("modelo")
    _montar(raiz)
    cfg = load_config(raiz)
    index_project(cfg)
    rebuild(cfg)
    return raiz


@pytest.fixture
def proj(modelo: Path, tmp_path: Path) -> Path:
    copia = tmp_path / "p"
    shutil.copytree(modelo, copia)
    return copia


def _tabela(conn: sqlite3.Connection, colunas: str, tabela: str, filtro: str) -> dict[str, tuple]:
    return {r[0]: tuple(r) for r in conn.execute(f"SELECT {colunas} FROM {tabela} WHERE {filtro}")}


def _grafo(cfg) -> tuple[dict[str, tuple], dict[str, tuple], dict[str, tuple], dict[str, tuple]]:
    """(entidades, relações) sem tecnologia, e as de tecnologia/`uses` à parte."""
    with open_db(cfg.db_path, read_only=True) as conn:
        return (
            _tabela(conn, _ENTIDADE, "entities", "type != 'technology'"),
            _tabela(conn, _RELACAO, "relations", "type != 'uses'"),
            _tabela(conn, _ENTIDADE, "entities", "type = 'technology'"),
            _tabela(conn, _RELACAO, "relations", "type = 'uses'"),
        )


def _comparar(cfg, contexto: str) -> None:
    """Grafo atual (incremental) contra o rebuild completo no mesmo banco."""
    inc_e, inc_r, inc_t, inc_u = _grafo(cfg)
    rebuild(cfg)
    ref_e, ref_r, ref_t, ref_u = _grafo(cfg)
    assert inc_e == ref_e, f"{contexto}: entidades diferem: {set(inc_e.items()) ^ set(ref_e.items())}"
    assert inc_r == ref_r, f"{contexto}: relações diferem: {set(inc_r.items()) ^ set(ref_r.items())}"
    assert ref_t.keys() <= inc_t.keys(), f"{contexto}: tecnologia perdida"
    assert ref_u.keys() <= inc_u.keys(), f"{contexto}: relação `uses` perdida"


def _editar(proj: Path, op: str, rng: random.Random) -> None:
    existentes = sorted(proj.glob("mod*.py"))
    arq = rng.choice(existentes)
    i = int(arq.stem[3:])
    if op == "corpo":
        arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", f"item * {rng.randrange(2, 90)} * ", 1), encoding="utf-8")
    elif op == "comentario":
        arq.write_text(arq.read_text(encoding="utf-8") + f"\n# nota {rng.random()}\n", encoding="utf-8")
    elif op == "simbolo_novo":
        arq.write_text(
            arq.read_text(encoding="utf-8")
            + f'\n\ndef extra_{rng.randrange(10**6)}(x):\n    """Funcao nova."""\n    total = Cls{i}().run(x)\n    total += x * 3\n    return total + {i}\n',
            encoding="utf-8",
        )
    elif op == "renomear":
        antigo = f"func_{i}"
        texto = arq.read_text(encoding="utf-8")
        if antigo in texto:
            arq.write_text(texto.replace(antigo, f"{antigo}_v{rng.randrange(1000)}"), encoding="utf-8")
    elif op == "arquivo_novo":
        n = N_MODULOS + rng.randrange(1000)
        (proj / f"mod{n}.py").write_text(_modulo(n, rng.randrange(N_MODULOS)), encoding="utf-8")
    elif op == "arquivo_removido":
        if arq.exists():
            arq.unlink()
    elif op == "doc":
        (proj / "servicos.md").write_text(
            DOC + f"\nO Cls{rng.randrange(N_MODULOS)} e o func_{rng.randrange(N_MODULOS)} aparecem aqui {rng.random()}.\n",
            encoding="utf-8",
        )
    elif op == "sql":
        (proj / "schema.sql").write_text(SCHEMA.replace("email TEXT NOT NULL", f"email TEXT NOT NULL,\n  nome{rng.randrange(99)} TEXT"), encoding="utf-8")
    elif op == "rota":
        (proj / "rotas.py").write_text(
            ROTAS.replace('"""Busca o usuario pelo id."""', f'"""Busca o usuario pelo id {rng.random()}."""'), encoding="utf-8"
        )
    else:  # pragma: no cover
        raise AssertionError(op)


OPERACOES = [
    "corpo", "comentario", "doc", "sql", "rota",  # nomes iguais: caminho rápido
    "simbolo_novo", "renomear", "arquivo_novo", "arquivo_removido",  # mudam o conjunto de nomes: completo
]
RAPIDAS = {"corpo", "comentario", "doc", "sql", "rota"}


@pytest.mark.parametrize("semente", range(50))
def test_sequencia_aleatoria_equivale_ao_rebuild(proj: Path, semente: int) -> None:
    """50 sequências de 3 edições: o incremental é igual ao completo depois de CADA passo."""
    rng = random.Random(semente)
    cfg = load_config(proj)
    for passo in range(3):
        op = rng.choice(OPERACOES)
        _editar(proj, op, rng)
        report = index_project(cfg)
        grafo = update_documents(cfg, report.touched_documents)
        if not report.touched_documents:
            assert grafo.documents == 0
        elif op in RAPIDAS:
            assert not grafo.fallback_full, f"semente {semente} passo {passo} {op}: caiu no completo ({grafo.reason})"
        _comparar(cfg, f"semente {semente} passo {passo} {op}")


def test_editar_corpo_nao_cai_no_completo(proj: Path) -> None:
    cfg = load_config(proj)
    arq = proj / "mod2.py"
    arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", "item * 7 * ", 1), encoding="utf-8")
    report = index_project(cfg)
    assert report.touched_documents == ["mod2.py"]
    grafo = update_documents(cfg, report.touched_documents)
    assert not grafo.fallback_full and grafo.documents == 1
    _comparar(cfg, "corpo")


def test_simbolo_novo_cai_no_completo_e_aparece_no_grafo(proj: Path) -> None:
    cfg = load_config(proj)
    arq = proj / "mod2.py"
    arq.write_text(
        arq.read_text(encoding="utf-8")
        + '\n\ndef recem_chegada(x):\n    """Nova."""\n    total = Cls2().run(x)\n    total += x * 3\n    return total + 2\n',
        encoding="utf-8",
    )
    report = index_project(cfg)
    grafo = update_documents(cfg, report.touched_documents)
    assert grafo.fallback_full and grafo.reason == "conjunto de entidades mudou"
    with open_db(cfg.db_path, read_only=True) as conn:
        achou = conn.execute("SELECT COUNT(*) FROM entities WHERE name = 'recem_chegada'").fetchone()[0]
    assert achou == 1


def test_manifesto_cai_no_completo(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "pyproject.toml").write_text(PYPROJECT.replace('"redis"', '"redis", "pydantic"'), encoding="utf-8")
    report = index_project(cfg)
    grafo = update_documents(cfg, report.touched_documents)
    assert grafo.fallback_full and grafo.reason == "manifesto de dependências"


def test_arquivo_removido_cai_no_completo(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "mod3.py").unlink()
    report = index_project(cfg)
    assert report.touched_documents == ["mod3.py"]
    grafo = update_documents(cfg, report.touched_documents)
    assert grafo.fallback_full
    _comparar(cfg, "removido")


def test_relacao_de_entrada_sobrevive_a_edicao_do_alvo(proj: Path) -> None:
    """mod1 chama Cls2 (de mod2): editar o CORPO de mod2 não pode perder a relação que vem de mod1."""
    cfg = load_config(proj)

    def entradas() -> set[tuple[str, str, str]]:
        with open_db(cfg.db_path, read_only=True) as conn:
            return {
                (r["src_id"], r["dst_id"], r["type"])
                for r in conn.execute(
                    "SELECT r.src_id, r.dst_id, r.type FROM relations r "
                    "JOIN entities s ON s.id = r.src_id JOIN entities d ON d.id = r.dst_id "
                    "WHERE s.qualified_name LIKE 'mod1.py%' AND d.document_id = "
                    "(SELECT id FROM documents WHERE rel_path = 'mod2.py') AND r.type = 'calls'"
                )
            }

    antes = entradas()
    assert antes, "o modelo devia ter uma chamada de mod1 para algo de mod2"
    arq = proj / "mod2.py"
    arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", "item * 11 * ", 1), encoding="utf-8")
    report = index_project(cfg)
    grafo = update_documents(cfg, report.touched_documents)
    assert not grafo.fallback_full
    assert entradas() == antes


def test_editar_uma_linha_nao_deixa_entidade_sem_chunk(proj: Path) -> None:
    """Sem o grafo incremental, editar um corpo zera `chunk_id` das entidades (o chunk muda de id)."""
    cfg = load_config(proj)
    arq = proj / "mod4.py"
    arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", "item * 5 * ", 1), encoding="utf-8")
    report = index_project(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        sem_antes = conn.execute("SELECT COUNT(*) FROM entities WHERE chunk_id IS NULL AND type != 'file'").fetchone()[0]
    assert sem_antes > 0, "a premissa do teste: o índice sozinho deixa pontes do grafo soltas"
    update_documents(cfg, report.touched_documents)
    with open_db(cfg.db_path, read_only=True) as conn:
        sem = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE chunk_id IS NULL AND type NOT IN ('file','technology')"
        ).fetchone()[0]
        sem_evidencia = conn.execute(
            "SELECT COUNT(*) FROM relations WHERE evidence_chunk_id IS NULL AND source IN ('structural','reference') "
            "AND type != 'uses'"
        ).fetchone()[0]
    assert sem == 0
    assert sem_evidencia == 0


def test_camada_semantica_nao_e_tocada(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path) as conn:
        conn.execute(
            "INSERT INTO entities(id, type, name, qualified_name, confidence, source) "
            "VALUES ('sem1','concept','servicos','servicos',0.8,'semantic')"
        )
        conn.execute(
            "INSERT INTO relations(id, src_id, dst_id, type, weight, confidence, source) "
            "SELECT 'sem-r1', 'sem1', id, 'mentions', 1.0, 0.7, 'semantic' FROM entities WHERE name = 'Cls2' LIMIT 1"
        )
        conn.commit()
    arq = proj / "mod2.py"
    arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", "item * 3 * ", 1), encoding="utf-8")
    report = index_project(cfg)
    grafo = update_documents(cfg, report.touched_documents)
    assert not grafo.fallback_full
    with open_db(cfg.db_path, read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM entities WHERE source = 'semantic'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM relations WHERE source = 'semantic'").fetchone()[0] == 1


def test_sem_grafo_construido_cai_no_completo(tmp_path: Path) -> None:
    _montar(tmp_path)
    cfg = load_config(tmp_path)
    report = index_project(cfg)
    grafo = update_documents(cfg, report.touched_documents[:1])
    assert grafo.fallback_full and grafo.reason == "grafo ainda não construído"


def test_lote_grande_cai_no_completo(proj: Path) -> None:
    cfg = load_config(proj)
    grafo = update_documents(cfg, [f"x{i}.py" for i in range(60)])
    assert grafo.fallback_full and "mais de" in (grafo.reason or "")


def test_sem_documentos_nao_faz_nada(proj: Path) -> None:
    grafo = update_documents(load_config(proj), [])
    assert not grafo.fallback_full and grafo.documents == 0


def test_touch_atualiza_o_grafo_e_falha_do_grafo_nao_devolve_o_lote(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx.indexing import touchq

    cfg = load_config(proj)
    arq = proj / "mod2.py"
    arq.write_text(arq.read_text(encoding="utf-8").replace("item * ", "item * 13 * ", 1), encoding="utf-8")
    touchq.enqueue(cfg.state_dir, ["mod2.py"])
    r = touchq.drain(cfg, wait_ms=0)
    assert r.indexed and r.graph_warning is None
    with open_db(cfg.db_path, read_only=True) as conn:
        sem = conn.execute("SELECT COUNT(*) FROM entities WHERE chunk_id IS NULL AND type NOT IN ('file','technology')").fetchone()[0]
    assert sem == 0

    def quebra(*a, **k):
        raise RuntimeError("grafo quebrado")

    monkeypatch.setattr("ragx.graph.service.update_documents", quebra)
    arq.write_text(arq.read_text(encoding="utf-8").replace("item * 13", "item * 14", 1), encoding="utf-8")
    touchq.enqueue(cfg.state_dir, ["mod2.py"])
    r = touchq.drain(cfg, wait_ms=0)
    assert r.indexed and r.error is None
    assert r.graph_warning is not None and "grafo quebrado" in r.graph_warning

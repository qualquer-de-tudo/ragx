"""`load_index`: vetorizado, idêntico ao laço por linha, e cacheado por geração.

Antes: `dequantize` e `l2_normalize` linha a linha em laço Python, a cada busca
(69-80 ms, ~75% do `search_hybrid` quente), e uma docstring prometendo um cache
que não existia. O cache é invalidado por `meta('vec_gen')`, mantido por gatilhos
em `embeddings`, e não por `mtime`, que não é confiável sob WAL.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0134-*.md`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from ragx.config import load_config
from ragx.embeddings.base import dequantize, l2_normalize, unpack_f32
from ragx.indexing.pipeline import index_project
from ragx.storage.db import open_db
from ragx.storage.vectors import (
    VectorIndex,
    load_index,
    reset_vector_cache,
    vec_generation,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def cache_limpo():
    reset_vector_cache()
    yield
    reset_vector_cache()


@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 96\nversioned_dim = 48\n',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    for i in range(6):
        (tmp_path / "src" / f"m{i}.py").write_text(
            f"def f{i}(x):\n    '''doc {i}'''\n    return x + {i}\n\n\n"
            f"class C{i}:\n    def g(self):\n        return {i * 7}\n",
            encoding="utf-8",
        )
    index_project(load_config(tmp_path))
    return tmp_path


def _antigo(conn: sqlite3.Connection, model_id: str) -> tuple[list[str], np.ndarray, np.ndarray | None]:
    """A versão por linha, copiada como referência do comportamento anterior."""
    rows = conn.execute(
        "SELECT chunk_id, vector, vector_q, q_scale, q_offset FROM embeddings WHERE model_id = ?",
        (model_id,),
    ).fetchall()
    ids = [r["chunk_id"] for r in rows]
    coarse = np.vstack(
        [l2_normalize(dequantize(r["vector_q"], r["q_scale"], r["q_offset"])) for r in rows]
    )
    full = None
    if all(r["vector"] is not None for r in rows):
        full = np.vstack([unpack_f32(r["vector"]) for r in rows])
    return ids, coarse, full


def test_load_index_e_identico_a_versao_por_linha(projeto: Path) -> None:
    cfg = load_config(projeto)
    with open_db(cfg.db_path, read_only=True) as conn:
        idx = load_index(conn)
        ids, coarse, full = _antigo(conn, idx.model_id)
    assert idx.ids == ids
    assert np.allclose(idx.coarse, coarse, atol=1e-6)
    assert idx.full is not None and full is not None
    assert np.array_equal(idx.full, full)
    assert idx.size > 10


def test_sem_vetor_local_o_estagio_grosseiro_continua_igual(projeto: Path) -> None:
    """Clone novo: só o int8 versionado existe (`vector` NULL)."""
    cfg = load_config(projeto)
    with open_db(cfg.db_path) as conn:
        conn.execute("UPDATE embeddings SET vector = NULL")
        conn.commit()
    with open_db(cfg.db_path, read_only=True) as conn:
        idx = load_index(conn)
        ids, coarse, full = _antigo(conn, idx.model_id)
    assert idx.full is None and full is None
    assert idx.ids == ids
    assert np.allclose(idx.coarse, coarse, atol=1e-6)


def test_segunda_chamada_devolve_o_mesmo_objeto(projeto: Path) -> None:
    cfg = load_config(projeto)
    with open_db(cfg.db_path, read_only=True) as conn:
        a = load_index(conn)
    with open_db(cfg.db_path, read_only=True) as conn:
        b = load_index(conn)
    assert isinstance(a, VectorIndex) and a is b


def test_gatilhos_mudam_a_geracao_e_invalidam_o_cache(projeto: Path) -> None:
    """INSERT, UPDATE e DELETE (inclusive em cascata) em `embeddings` invalidam."""
    cfg = load_config(projeto)
    with open_db(cfg.db_path, read_only=True) as conn:
        g0 = vec_generation(conn)
        a = load_index(conn)
    assert g0 is not None

    # UPDATE
    with open_db(cfg.db_path) as conn:
        conn.execute("UPDATE embeddings SET created_at = created_at WHERE rowid = 1")
        conn.commit()
    with open_db(cfg.db_path, read_only=True) as conn:
        g1 = vec_generation(conn)
        b = load_index(conn)
    assert g1 is not None and g1 > g0 and b is not a

    # DELETE em cascata (apagar o documento apaga chunks e embeddings)
    with open_db(cfg.db_path) as conn:
        conn.execute("DELETE FROM documents WHERE rel_path = 'src/m0.py'")
        conn.commit()
    with open_db(cfg.db_path, read_only=True) as conn:
        g2 = vec_generation(conn)
        c = load_index(conn)
    assert g2 is not None and g2 > g1 and c is not b
    assert c.size < b.size

    # INSERT OR REPLACE
    with open_db(cfg.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO embeddings SELECT * FROM embeddings WHERE rowid = "
            "(SELECT MIN(rowid) FROM embeddings)"
        )
        conn.commit()
    with open_db(cfg.db_path, read_only=True) as conn:
        g3 = vec_generation(conn)
        d = load_index(conn)
    assert g3 is not None and g3 > g2 and d is not c


def test_reindexar_um_arquivo_invalida_o_cache(projeto: Path) -> None:
    cfg = load_config(projeto)
    with open_db(cfg.db_path, read_only=True) as conn:
        antes = load_index(conn)
    (projeto / "src" / "m1.py").write_text("def novo():\n    return 'texto novo'\n", encoding="utf-8")
    index_project(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        depois = load_index(conn)
    assert depois is not antes
    assert depois.ids != antes.ids


def test_banco_sem_vec_gen_nao_usa_cache(projeto: Path) -> None:
    """Banco aberto em modo leitura de uma versão antiga do esquema: sem a chave,
    recarrega sempre em vez de arriscar servir índice velho."""
    cfg = load_config(projeto)
    with open_db(cfg.db_path) as conn:
        conn.execute("DELETE FROM meta WHERE key = 'vec_gen'")
        conn.commit()
    with open_db(cfg.db_path, read_only=True) as conn:
        assert vec_generation(conn) is None
        a = load_index(conn)
        b = load_index(conn)
    assert a is not b
    assert a.ids == b.ids


def test_banco_vazio_devolve_indice_vazio(tmp_path: Path) -> None:
    with open_db(tmp_path / "x.db") as conn:
        idx = load_index(conn)
    assert idx.size == 0


def test_resolve_model_e_deterministico_com_o_mesmo_created_at(tmp_path: Path) -> None:
    from ragx.storage.vectors import _resolve_model, register_model

    with open_db(tmp_path / "x.db") as conn:
        register_model(conn, "a:um", 8, 4)
        register_model(conn, "b:dois", 8, 4)
        conn.execute("UPDATE embedding_models SET created_at = '2026-01-01T00:00:00Z'")
        conn.commit()
        escolhidos = {_resolve_model(conn, None)["id"] for _ in range(5)}  # type: ignore[index]
    assert escolhidos == {"b:dois"}  # o inserido por último vence o empate

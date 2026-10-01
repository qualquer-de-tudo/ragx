"""`ChunkRepo.replace_for_document` preserva o que não mudou (RAGX-0138).

Era "apaga tudo e reinsere": como `embeddings.chunk_id` é `ON DELETE CASCADE` e
`entities.chunk_id` / `relations.evidence_chunk_id` são `ON DELETE SET NULL`, editar
um arquivo derrubava os vetores e as pontes do grafo de TODOS os chunks dele, mesmo
dos que não mudaram. Como o `chunk.id` é hash de (caminho, conteúdo, versão), o id já
é o diff: quem tem o mesmo id sobrevive.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pytest

from ragx.core.models import Chunk, ChunkKind, DocKind, Document
from ragx.storage.db import open_db
from ragx.storage.repositories import ChunkRepo, DocumentRepo

pytestmark = pytest.mark.integration

DOC = "doc-1"


def _chunk(i: int, ordinal: int, parent: str | None = None, symbol: str | None = None,
           heading: str | None = None, kind: ChunkKind = ChunkKind.FUNCTION,
           texto: str | None = None) -> Chunk:
    cid = f"{i:032x}"
    corpo = texto if texto is not None else f"conteudo do chunk {i}"
    return Chunk(
        id=cid, document_id=DOC, ordinal=ordinal, kind=kind, start_line=ordinal * 10 + 1,
        end_line=ordinal * 10 + 9, content=corpo, content_hash=f"h{i}", token_count=5 + i,
        symbol=symbol if symbol is not None else f"sim{i}", heading_path=heading, parent_id=parent,
    )


@pytest.fixture
def conn(tmp_path: Path):
    with open_db(tmp_path / "t.db") as c:
        DocumentRepo(c).upsert(Document(
            id=DOC, rel_path="a.py", doc_kind=DocKind.CODE, size_bytes=1, mtime_ns=1,
            content_hash="x", chunker_version="1", lang="python", title=None, redacted=False,
        ))
        c.execute("INSERT INTO embedding_models(id, dim, versioned_dim, quant, normalized, created_at) "
                  "VALUES ('m', 4, 4, 'int8', 1, 'now')")
        c.commit()
        yield c


def _vetores_e_pontes(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
    """Um embedding por chunk, e uma entidade que aponta para o chunk (a ponte do grafo)."""
    for c in chunks:
        conn.execute(
            "INSERT INTO embeddings(chunk_id, model_id, vector, vector_q, q_scale, q_offset, created_at) "
            "VALUES (?, 'm', NULL, ?, 1.0, 0.0, 'now')", (c.id, b"\x00\x01\x02\x03"),
        )
        conn.execute(
            "INSERT INTO entities(id, type, name, qualified_name, document_id, chunk_id, source) "
            "VALUES (?, 'function', ?, ?, ?, ?, 'structural')", (f"e{c.id}", c.symbol, f"a.py::{c.symbol}", DOC, c.id),
        )
    conn.commit()


def _n(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def _estado(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(r) for r in conn.execute(
        "SELECT id, ordinal, parent_id, kind, symbol, heading_path, start_line, end_line, "
        "content, content_hash, token_count FROM chunks WHERE document_id = ? ORDER BY ordinal", (DOC,))]


def _19() -> list[Chunk]:
    return [_chunk(i, i) for i in range(19)]


def test_reinserir_os_mesmos_chunks_nao_derruba_vetores_nem_pontes(conn) -> None:
    repo = ChunkRepo(conn)
    repo.replace_for_document(DOC, _19())
    _vetores_e_pontes(conn, _19())
    assert (_n(conn, "SELECT COUNT(*) FROM embeddings"),
            _n(conn, "SELECT COUNT(*) FROM entities WHERE chunk_id IS NOT NULL")) == (19, 19)

    antes = conn.total_changes
    stats = repo.replace_for_document(DOC, _19())

    # RAGX-0138: antes 19 -> 0 embeddings e pontes 19 -> 0
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 19
    assert _n(conn, "SELECT COUNT(*) FROM entities WHERE chunk_id IS NOT NULL") == 19
    assert conn.total_changes == antes, "reinserir o mesmo conteúdo não escreve nada"
    assert (stats.kept, stats.added, stats.removed, stats.updated) == (19, 0, 0, 0)


def test_editar_um_chunk_so_ele_sai_e_entra(conn) -> None:
    repo = ChunkRepo(conn)
    repo.replace_for_document(DOC, _19())
    _vetores_e_pontes(conn, _19())
    criados = {r[0]: r[1] for r in conn.execute("SELECT id, created_at FROM chunks")}

    editado = _19()
    editado[7] = _chunk(700, 7, texto="conteudo NOVO")  # outro id = outro conteúdo
    stats = repo.replace_for_document(DOC, editado)

    assert (stats.kept, stats.added, stats.removed) == (18, 1, 1)
    assert _n(conn, "SELECT COUNT(*) FROM chunks") == 19
    # os 18 intactos mantêm created_at, vetor e ponte
    for cid, quando in criados.items():
        if cid != f"{7:032x}":
            assert conn.execute("SELECT created_at FROM chunks WHERE id = ?", (cid,)).fetchone()[0] == quando
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 18  # o editado perdeu o vetor e vai ao embedder
    assert _n(conn, "SELECT COUNT(*) FROM entities WHERE chunk_id IS NOT NULL") == 18


def test_inserir_no_meio_e_trocar_de_lugar_nao_viola_unique(conn) -> None:
    repo = ChunkRepo(conn)
    base = [_chunk(i, i) for i in range(6)]
    repo.replace_for_document(DOC, base)
    _vetores_e_pontes(conn, base)

    meio = base[:3] + [_chunk(99, 3)] + [_chunk(i, i + 1) for i in range(3, 6)]
    repo.replace_for_document(DOC, meio)
    assert [r[0] for r in conn.execute("SELECT ordinal FROM chunks ORDER BY ordinal")] == list(range(7))
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 6  # os 6 sobreviveram ao deslocamento

    trocado = list(meio)
    trocado[0], trocado[1] = _chunk(1, 0), _chunk(0, 1)
    repo.replace_for_document(DOC, trocado)
    assert [r[0] for r in conn.execute("SELECT id FROM chunks ORDER BY ordinal LIMIT 2")] == [f"{1:032x}", f"{0:032x}"]
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 6


def test_pai_removido_com_filho_vivo_o_filho_sobrevive_com_o_novo_pai(conn) -> None:
    repo = ChunkRepo(conn)
    pai = _chunk(1, 0, kind=ChunkKind.CLASS)
    filho = _chunk(2, 1, parent=pai.id, kind=ChunkKind.METHOD)
    repo.replace_for_document(DOC, [pai, filho])
    _vetores_e_pontes(conn, [filho])

    novo_pai = _chunk(3, 0, kind=ChunkKind.CLASS)
    repo.replace_for_document(DOC, [novo_pai, _chunk(2, 1, parent=novo_pai.id, kind=ChunkKind.METHOD)])

    assert conn.execute("SELECT parent_id FROM chunks WHERE id = ?", (filho.id,)).fetchone()[0] == novo_pai.id
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 1, "o vetor do filho tinha de sobreviver"


def test_mudou_o_prefixo_de_contexto_o_vetor_velho_e_descartado_so_desse_chunk(conn) -> None:
    repo = ChunkRepo(conn)
    base = [_chunk(i, i, heading="H") for i in range(4)]
    repo.replace_for_document(DOC, base)
    _vetores_e_pontes(conn, base)

    novo = list(base)
    novo[2] = _chunk(2, 2, heading="OUTRO")  # mesmo id, outro `heading_path`
    stats = repo.replace_for_document(DOC, novo)

    assert stats.updated == 1
    assert conn.execute("SELECT heading_path FROM chunks WHERE id = ?", (f"{2:032x}",)).fetchone()[0] == "OUTRO"
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 3
    assert _n(conn, f"SELECT COUNT(*) FROM embeddings WHERE chunk_id = '{2:032x}'") == 0


def test_remover_o_documento_continua_limpando_tudo_em_cascata(conn) -> None:
    repo = ChunkRepo(conn)
    repo.replace_for_document(DOC, _19())
    _vetores_e_pontes(conn, _19())
    conn.execute("DELETE FROM documents WHERE id = ?", (DOC,))
    conn.commit()
    assert _n(conn, "SELECT COUNT(*) FROM chunks") == 0
    assert _n(conn, "SELECT COUNT(*) FROM embeddings") == 0


def test_fts_acompanha_o_diff_e_o_termo_removido_nao_aparece(conn) -> None:
    repo = ChunkRepo(conn)
    repo.replace_for_document(DOC, [_chunk(1, 0, texto="alfa unico"), _chunk(2, 1, texto="beta unico")])
    repo.replace_for_document(DOC, [_chunk(1, 0, texto="alfa unico"), _chunk(3, 1, texto="gama unico")])
    achou = lambda t: _n(conn, f"SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH '{t}'")  # noqa: E731
    assert achou("alfa") == 1 and achou("gama") == 1 and achou("beta") == 0
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")  # levanta se houver divergência


def _apagar_e_reinserir(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (DOC,))
    ChunkRepo(conn).replace_for_document(DOC, chunks)


def _sequencia(rng: random.Random) -> list[Chunk]:
    """Uma lista de chunks válida: ids sorteados de um conjunto pequeno (muita sobreposição entre
    rodadas), pais sempre ANTES dos filhos e conteúdo/símbolo/título estáveis POR ID, que é
    o que o chunker garante (mesmo id = mesmo conteúdo)."""
    n = rng.randint(0, 9)
    ids = rng.sample(range(14), n)
    out: list[Chunk] = []
    for ordinal, i in enumerate(ids):
        pai = None
        if out and rng.random() < 0.4:
            pai = rng.choice(out).id
        out.append(_chunk(i, ordinal, parent=pai, heading=f"H{i % 3}",
                          kind=ChunkKind.METHOD if pai else ChunkKind.FUNCTION))
    return out


def test_equivale_a_apagar_e_reinserir_em_200_sequencias_sorteadas(tmp_path: Path) -> None:
    rng = random.Random(20260930)
    with open_db(tmp_path / "a.db") as por_diff, open_db(tmp_path / "b.db") as por_apagar:
        for c in (por_diff, por_apagar):
            DocumentRepo(c).upsert(Document(
                id=DOC, rel_path="a.py", doc_kind=DocKind.CODE, size_bytes=1, mtime_ns=1,
                content_hash="x", chunker_version="1", lang="python", title=None, redacted=False))
            c.commit()
        for passo in range(200):
            chunks = _sequencia(rng)
            ChunkRepo(por_diff).replace_for_document(DOC, chunks)
            _apagar_e_reinserir(por_apagar, chunks)
            por_diff.commit()
            por_apagar.commit()
            assert _estado(por_diff) == _estado(por_apagar), f"divergiu no passo {passo}"
        por_diff.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")

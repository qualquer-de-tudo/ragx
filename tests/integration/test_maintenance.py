"""Fase 10 — manutenção, robustez e recuperação."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project, status
from ragx.storage.db import integrity_check, open_db

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("class A:\n    def m(self):\n        return 1\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n\nTexto.\n", encoding="utf-8")
    index_project(load_config(tmp_path))
    return tmp_path


def test_vacuum_remove_orfaos(proj: Path) -> None:
    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO embeddings(chunk_id, model_id, vector_q, q_scale, q_offset, created_at) "
        "VALUES ('orfao', (SELECT id FROM embedding_models LIMIT 1), X'00', 1.0, 0.0, 'x')"
    )
    conn.commit()
    conn.close()

    from ragx.cli.commands.maintenance_cmd import _ORPHAN_QUERIES

    with open_db(cfg.db_path) as c:
        removidos = sum((c.execute(sql).rowcount or 0) for _label, sql in _ORPHAN_QUERIES)
        c.commit()
    assert removidos >= 1

    conn = sqlite3.connect(cfg.db_path)
    n = conn.execute("SELECT COUNT(*) FROM embeddings WHERE chunk_id = 'orfao'").fetchone()[0]
    conn.close()
    assert n == 0


def test_vacuum_nao_perde_dado_valido(proj: Path) -> None:
    from ragx.cli.commands.maintenance_cmd import _ORPHAN_QUERIES

    cfg = load_config(proj)
    antes = status(cfg)
    with open_db(cfg.db_path) as c:
        for _label, sql in _ORPHAN_QUERIES:
            c.execute(sql)
        c.commit()
    assert status(cfg)["chunks"] == antes["chunks"]
    assert status(cfg)["documents"] == antes["documents"]


def test_integridade_do_banco(proj: Path) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path, read_only=True) as conn:
        assert integrity_check(conn) == "ok"


def test_doctor_detecta_inconsistencia_injetada(proj: Path) -> None:
    from ragx.cli.commands.doctor import _orphans

    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM documents")
    conn.commit()
    conn.close()

    with open_db(cfg.db_path, read_only=True) as c:
        orfaos = _orphans(c)
    assert orfaos["chunks sem documento"] > 0


def test_reset_e_reconstrucao(proj: Path) -> None:
    import shutil

    cfg = load_config(proj)
    antes = status(cfg)["chunks"]
    shutil.rmtree(cfg.state_dir)
    assert not cfg.db_path.exists()
    index_project(cfg)
    assert status(cfg)["chunks"] == antes


# ── robustez (docs/13) ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "nome,conteudo",
    [
        ("bom.py", b"\xef\xbb\xbfdef f():\n    return 1\n"),          # BOM
        ("latin.py", "def f():\n    return 'ç'\n".encode("latin-1")),  # latin-1
        ("vazio.py", b""),                                             # vazio
        ("um.py", b"x"),                                               # 1 byte
        ("sem_nl.py", b"def f():\n    return 1"),                      # sem newline final
        ("crlf.py", b"def f():\r\n    return 1\r\n"),                  # CRLF
        ("misto.py", b"def f():\r\n    return 1\n"),                   # CRLF misturado
    ],
)
def test_arquivos_de_borda_nao_quebram(tmp_path: Path, nome: str, conteudo: bytes) -> None:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / nome).write_bytes(conteudo)
    r = index_project(load_config(tmp_path))
    assert r.stats.files_seen >= 1


@pytest.mark.parametrize("nome", ["com espaço.py", "acentuação.py", "emoji_🚀.py"])
def test_nomes_de_arquivo_dificeis(tmp_path: Path, nome: str) -> None:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 32\n',
        encoding="utf-8",
    )
    try:
        (tmp_path / nome).write_text("def f():\n    return 1\n", encoding="utf-8")
    except OSError:
        pytest.skip(f"sistema de arquivos não aceita {nome!r}")
    r = index_project(load_config(tmp_path))
    assert r.stats.indexed >= 1


def test_arquivo_binario_e_pulado(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "dados.py").write_bytes(b"\x00\x01\x02binario")
    r = index_project(load_config(tmp_path))
    assert r.stats.skip_reasons.get("binary", 0) >= 1


def test_arquivo_grande_demais_e_pulado(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[index]\nmax_file_bytes = 100\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "grande.py").write_text("# " + "x" * 500 + "\n", encoding="utf-8")
    r = index_project(load_config(tmp_path))
    assert r.stats.skip_reasons.get("too_large", 0) >= 1


def test_banco_corrompido_da_mensagem_clara(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.db_path.write_bytes(b"isto nao e um banco sqlite" * 50)
    with pytest.raises(Exception) as exc, open_db(cfg.db_path) as conn:
        conn.execute("SELECT 1 FROM meta")
    assert "meta" in str(exc.value).lower() or "database" in str(exc.value).lower()


def test_schema_futuro_e_recusado(tmp_path: Path) -> None:
    from ragx.core.errors import EnvError

    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    with open_db(cfg.db_path) as conn:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
    with pytest.raises(EnvError, match="atualize"), open_db(cfg.db_path):
        pass


def test_reindexacao_apos_interrupcao_converge(proj: Path) -> None:
    """Ctrl+C e reexecução chegam ao mesmo estado de uma execução inteira."""
    cfg = load_config(proj)
    esperado = status(cfg)
    with open_db(cfg.db_path) as conn:
        conn.execute("DELETE FROM chunks WHERE ordinal > 0")
        conn.commit()
    index_project(cfg, full=True)
    assert status(cfg)["chunks"] == esperado["chunks"]

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project, status

pytestmark = pytest.mark.integration


# O próprio ragx.toml também é indexado (.toml está na lista suportada).
N_DOCS = 4


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        # provider determinístico: testes de pipeline não podem depender de daemon
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "a.py").write_text(
        "import os\n\n\nclass A:\n    def m(self):\n        return os.name\n", encoding="utf-8"
    )
    (tmp_path / "src" / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "docs" / "d.md").write_text("# T\n\n## S\n\ntexto\n", encoding="utf-8")
    return tmp_path


def test_indexa_e_conta(proj: Path) -> None:
    cfg = load_config(proj)
    r = index_project(cfg)
    assert r.stats.indexed == N_DOCS
    assert r.new_documents == N_DOCS
    assert r.new_chunks > 0
    assert status(cfg)["documents"] == N_DOCS


def test_segunda_execucao_nao_recria_nada(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    r2 = index_project(cfg)
    assert r2.new_documents == 0
    assert r2.new_chunks == 0
    assert r2.stats.unchanged == N_DOCS


def test_modificacao_reindexa_so_o_arquivo(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    r = index_project(cfg)
    assert r.modified_documents == 1 and r.new_documents == 0
    assert r.stats.unchanged == N_DOCS - 1


def test_mudanca_so_de_indentacao_final_nao_gera_chunk_novo(proj: Path) -> None:
    """A normalização de ID remove trailing whitespace — commit de formatação
    não pode sujar o índice."""
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").write_text("def f():   \n    return 1\t\n", encoding="utf-8")
    r = index_project(cfg)
    assert r.new_chunks == 0, "trailing whitespace não pode gerar chunk novo"


def test_arquivo_removido_some_do_indice(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").unlink()
    r = index_project(cfg)
    assert r.stats.removed == 1
    assert status(cfg)["documents"] == N_DOCS - 1


def test_delete_em_cascata_nao_deixa_orfao(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "a.py").unlink()
    index_project(cfg)
    conn = sqlite3.connect(cfg.db_path)
    orfaos = conn.execute(
        "SELECT COUNT(*) FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
        "WHERE d.id IS NULL"
    ).fetchone()[0]
    fts = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert orfaos == 0
    assert fts == n, "índice FTS dessincronizado dos chunks"


def test_full_reindexa_tudo(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    r = index_project(cfg, full=True)
    assert r.stats.indexed == N_DOCS and r.stats.unchanged == 0


def test_dry_run_nao_escreve(proj: Path) -> None:
    cfg = load_config(proj)
    r = index_project(cfg, dry_run=True)
    assert r.stats.indexed == N_DOCS
    assert not cfg.db_path.exists() or status(cfg).get("documents", 0) == 0


def test_arquivo_que_vira_sensivel_e_removido(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    assert status(cfg)["documents"] == N_DOCS
    (proj / "src" / "b.py").write_text(
        'KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8"
    )
    r = index_project(cfg)
    assert r.stats.blocked == 1
    assert status(cfg)["documents"] == N_DOCS - 1


def test_run_e_registrado(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    run = status(cfg)["last_run"]
    assert run and run["mode"] == "incremental" and run["finished_at"]


def test_excecao_real_propaga_e_fica_registrada_como_erro(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão: o `finally` de `_index_once` só sabia gravar `error` para
    Ctrl+C (`report.interrupted`) — qualquer outra exceção media o laço
    quebrava para fora e a corrida ficava registrada como limpa
    (`error=None`), contando depois como "última indexação útil"."""
    from ragx.indexing import pipeline
    from ragx.storage.db import open_db

    cfg = load_config(proj)

    def _boom(*a: object, **kw: object) -> None:
        raise ValueError("falha simulada no meio do laco")

    monkeypatch.setattr(pipeline, "chunk_document", _boom)
    with pytest.raises(ValueError, match="falha simulada"):
        index_project(cfg)

    with open_db(cfg.db_path) as conn:
        row = conn.execute(
            "SELECT error, finished_at FROM index_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["finished_at"] is not None
    assert row["error"] is not None and "falha simulada" in row["error"]

    # a corrida quebrada não pode ser escolhida como "última indexação útil"
    fr = status(cfg)["freshness"]
    assert fr["state"] == "unknown"


def test_acentuacao_casa_no_fts(proj: Path) -> None:
    (proj / "docs" / "acento.md").write_text(
        "# Autenticação\n\nO fluxo de autenticação usa SSO.\n", encoding="utf-8"
    )
    cfg = load_config(proj)
    index_project(cfg)
    conn = sqlite3.connect(cfg.db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", ("autenticacao",)
    ).fetchone()[0]
    conn.close()
    assert n > 0, "remove_diacritics não está ativo"

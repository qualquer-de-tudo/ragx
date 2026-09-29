"""O teste de FTS5 não pode confundir banco ocupado com Python sem FTS5."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.storage import db

pytestmark = pytest.mark.unit


def test_banco_ocupado_por_outro_escritor_nao_vira_erro_de_fts5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    caminho = tmp_path / "knowledge.db"
    db.connect(caminho).close()

    # Outro processo (o painel indexando, um hook de commit) segura a escrita.
    dono = sqlite3.connect(caminho)
    dono.execute("CREATE TABLE IF NOT EXISTS t (x)")
    dono.execute("BEGIN IMMEDIATE")
    dono.execute("INSERT INTO t VALUES (1)")
    # Sem espera: o teste não pode levar os 5 s do busy_timeout real.
    monkeypatch.setattr(db, "_PRAGMAS", tuple(p for p in db._PRAGMAS if p[0] != "busy_timeout"))
    try:
        conn = db.connect(caminho)
        conn.close()
    finally:
        dono.rollback()
        dono.close()


def test_sem_fts5_a_mensagem_continua_clara(monkeypatch: pytest.MonkeyPatch) -> None:
    db._fts5_disponivel.cache_clear()
    monkeypatch.setattr(db, "_sonda_fts5", lambda: False)
    try:
        with pytest.raises(db.EnvError, match="FTS5"):
            db._require_fts5()
    finally:
        db._fts5_disponivel.cache_clear()

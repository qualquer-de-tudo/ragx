"""Conexão SQLite, pragmas e runner de migrações.

Sem ORM e sem Alembic: o schema é pequeno e explícito, controlado por
PRAGMA user_version. Ver docs/03-modelo-de-dados.md.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ragx.core.errors import EnvError

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_PRAGMAS = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
    ("busy_timeout", "5000"),
    ("temp_store", "MEMORY"),
    ("mmap_size", "268435456"),
)


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path, read_only: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if read_only:
        if not path.exists():
            raise EnvError(f"banco não encontrado: {path}")
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for key, value in _PRAGMAS:
        if read_only and key in ("journal_mode", "synchronous"):
            continue
        conn.execute(f"PRAGMA {key} = {value}")
    # O probe de FTS5 CRIA uma tabela — impossível em modo ro, e desnecessário:
    # o banco só existe porque foi criado com FTS5 disponível.
    if not read_only:
        _require_fts5(conn)
    return conn


def _require_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
    except sqlite3.OperationalError as exc:
        raise EnvError(
            "este Python foi compilado sem FTS5; a busca por palavra-chave depende dele.\n"
            "  → instale um Python com SQLite >= 3.9 com FTS5 habilitado"
        ) from exc


def _migrations() -> list[tuple[int, Path]]:
    out = []
    for f in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        out.append((int(f.name[:4]), f))
    return out


def user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Aplica migrações pendentes, cada uma em sua transação. Idempotente."""
    current = user_version(conn)
    available = _migrations()
    latest = available[-1][0] if available else 0
    if current > latest:
        raise EnvError(
            f"banco na versão {current}, mas esta instalação suporta até {latest}.\n"
            "  → atualize o RAGX (uv tool upgrade ragx)"
        )
    applied = 0
    for version, path in available:
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.execute("BEGIN")
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied += 1
    return applied


@contextmanager
def open_db(path: Path, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect(path, read_only=read_only)
    try:
        if not read_only:
            migrate(conn)
        yield conn
    finally:
        conn.close()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def integrity_check(conn: sqlite3.Connection) -> str:
    return str(conn.execute("PRAGMA integrity_check").fetchone()[0])

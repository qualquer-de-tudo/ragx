"""Repositórios. SQL explícito, sem ORM."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from ragx.core.models import Chunk, ChunkKind, DocKind, Document, SecurityFinding
from ragx.storage.db import utcnow

if TYPE_CHECKING:
    from ragx.gitinfo import GitState


class DocumentRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def fingerprints(self) -> dict[str, tuple[str, int, int, str]]:
        """rel_path -> (content_hash, size, mtime_ns, chunker_version). Base do
        atalho de incrementalidade."""
        return {
            r["rel_path"]: (r["content_hash"], r["size_bytes"], r["mtime_ns"], r["chunker_version"])
            for r in self.conn.execute(
                "SELECT rel_path, content_hash, size_bytes, mtime_ns, chunker_version FROM documents"
            )
        }

    def upsert(self, doc: Document) -> None:
        self.conn.execute(
            """INSERT INTO documents
               (id, rel_path, lang, doc_kind, size_bytes, mtime_ns, content_hash,
                redacted, title, indexed_at, chunker_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 lang=excluded.lang, doc_kind=excluded.doc_kind,
                 size_bytes=excluded.size_bytes, mtime_ns=excluded.mtime_ns,
                 content_hash=excluded.content_hash, redacted=excluded.redacted,
                 title=excluded.title, indexed_at=excluded.indexed_at,
                 chunker_version=excluded.chunker_version""",
            (
                doc.id, doc.rel_path, doc.lang, doc.doc_kind.value, doc.size_bytes,
                doc.mtime_ns, doc.content_hash, int(doc.redacted), doc.title,
                utcnow(), doc.chunker_version,
            ),
        )

    def delete_many(self, rel_paths: Iterable[str]) -> int:
        paths = list(rel_paths)
        if not paths:
            return 0
        self.conn.executemany("DELETE FROM documents WHERE rel_path = ?", [(p,) for p in paths])
        return len(paths)

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])

    def list(
        self, lang: str | None = None, kind: str | None = None,
        path_like: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM documents WHERE 1=1"
        args: list[Any] = []
        if lang:
            sql += " AND lang = ?"
            args.append(lang)
        if kind:
            sql += " AND doc_kind = ?"
            args.append(kind)
        if path_like:
            sql += " AND rel_path LIKE ?"
            args.append(path_like.replace("*", "%"))
        sql += " ORDER BY rel_path LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args)]

    def get(self, rel_path: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM documents WHERE rel_path = ?", (rel_path,)).fetchone()
        return dict(r) if r else None


class ChunkRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_for_document(self, doc_id: str, chunks: Sequence[Chunk]) -> int:
        """Delete + insert: reindexar documento modificado não pode duplicar."""
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        now = utcnow()
        self.conn.executemany(
            """INSERT INTO chunks
               (id, document_id, ordinal, parent_id, kind, symbol, heading_path,
                start_line, end_line, content, content_hash, token_count, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    c.id, c.document_id, c.ordinal, c.parent_id, c.kind.value, c.symbol,
                    c.heading_path, c.start_line, c.end_line, c.content, c.content_hash,
                    c.token_count, now,
                )
                for c in chunks
            ],
        )
        return len(chunks)

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def for_document(self, rel_path: str, limit: int = 500) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT c.* FROM chunks c JOIN documents d ON d.id = c.document_id
                   WHERE d.rel_path = ? ORDER BY c.ordinal LIMIT ?""",
                (rel_path, limit),
            )
        ]

    def get(self, chunk_id: str) -> dict[str, Any] | None:
        r = self.conn.execute(
            """SELECT c.*, d.rel_path FROM chunks c JOIN documents d ON d.id = c.document_id
               WHERE c.id = ?""",
            (chunk_id,),
        ).fetchone()
        return dict(r) if r else None

    def neighbors(self, chunk_id: str) -> list[dict[str, Any]]:
        row = self.get(chunk_id)
        if not row:
            return []
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT * FROM chunks WHERE document_id = ?
                   AND ordinal BETWEEN ? AND ? ORDER BY ordinal""",
                (row["document_id"], row["ordinal"] - 1, row["ordinal"] + 1),
            )
        ]

    def missing_from(self, known: Iterable[str]) -> list[str]:
        known_set = set(known)
        return [
            r["rel_path"]
            for r in self.conn.execute("SELECT rel_path FROM documents")
            if r["rel_path"] not in known_set
        ]


class SecurityEventRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, run_id: int | None, findings: Iterable[SecurityFinding]) -> int:
        rows = [
            (run_id, f.path, f.rule_id, f.severity.value, f.action.value, f.line,
             f.digest, f.preview, utcnow())
            for f in findings
        ]
        if not rows:
            return 0
        self.conn.executemany(
            """INSERT INTO security_events
               (run_id, path, rule_id, severity, action, line, digest, preview, detected_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        return len(rows)

    def clear_for(self, rel_path: str) -> None:
        self.conn.execute("DELETE FROM security_events WHERE path = ?", (rel_path,))

    def summary(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT path, rule_id, severity, action, line, preview
                   FROM security_events ORDER BY severity DESC, path"""
            )
        ]


class RunRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def start(self, mode: str, source: str = "cli", git: GitState | None = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO index_runs(started_at, mode, source, git_branch, git_commit, git_dirty)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                utcnow(), mode, source,
                git.branch if git else None,
                git.commit if git else None,
                (1 if git.dirty else 0) if git else None,
            ),
        )
        return int(cur.lastrowid or 0)

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM index_runs ORDER BY id DESC LIMIT ?", (limit,)
            )
        ]

    def finish(self, run_id: int, stats: dict[str, int], error: str | None = None) -> None:
        self.conn.execute(
            """UPDATE index_runs SET finished_at=?, files_seen=?, indexed=?, skipped=?,
               blocked=?, removed=?, chunks=?, embedded=?, duration_ms=?, error=?
               WHERE id=?""",
            (
                utcnow(), stats.get("files_seen", 0), stats.get("indexed", 0),
                stats.get("skipped", 0), stats.get("blocked", 0), stats.get("removed", 0),
                stats.get("chunks", 0), stats.get("embedded", 0),
                stats.get("duration_ms", 0), error, run_id,
            ),
        )

    def latest(self) -> dict[str, Any] | None:
        r = self.conn.execute(
            "SELECT * FROM index_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else None


def row_to_chunk(row: dict[str, Any]) -> Chunk:
    return Chunk(
        id=row["id"], document_id=row["document_id"], ordinal=row["ordinal"],
        kind=ChunkKind(row["kind"]), start_line=row["start_line"], end_line=row["end_line"],
        content=row["content"], content_hash=row["content_hash"],
        token_count=row["token_count"], symbol=row["symbol"],
        heading_path=row["heading_path"], parent_id=row["parent_id"],
    )


def row_to_document(row: dict[str, Any]) -> Document:
    return Document(
        id=row["id"], rel_path=row["rel_path"], doc_kind=DocKind(row["doc_kind"]),
        size_bytes=row["size_bytes"], mtime_ns=row["mtime_ns"],
        content_hash=row["content_hash"], chunker_version=row["chunker_version"],
        lang=row["lang"], title=row["title"], redacted=bool(row["redacted"]),
    )

"""Repositórios. SQL explícito, sem ORM."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
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


@dataclass
class ReplaceStats:
    """O que `ChunkRepo.replace_for_document` fez: quantos chunks ficaram, entraram, saíram
    e tiveram a linha atualizada (mesmo id, outra posição ou metadado)."""

    kept: int = 0
    added: int = 0
    removed: int = 0
    updated: int = 0


class ChunkRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_for_document(self, doc_id: str, chunks: Sequence[Chunk]) -> ReplaceStats:
        """Troca os chunks do documento PRESERVANDO os que não mudaram.

        O `chunk.id` é hash de (caminho, conteúdo normalizado, versão): quem tem o mesmo id
        tem o mesmo conteúdo e sobrevive. Antes era "apaga tudo e reinsere", e como
        `embeddings.chunk_id` é `ON DELETE CASCADE` e `entities.chunk_id` /
        `relations.evidence_chunk_id` são `ON DELETE SET NULL`, editar UMA linha derrubava os
        vetores e as pontes do grafo de todos os chunks do arquivo (RAGX-0138).

        A ordem importa, porque `UNIQUE (document_id, ordinal)` é checado a cada instrução, e
        `parent_id` é `ON DELETE CASCADE`:
        1. sobrevivente cujo pai vai sair: `parent_id = NULL` (senão o cascade o apaga);
        2. apaga os removidos;
        3. sobrevivente que muda de `ordinal` vai para um valor negativo provisório;
        4. insere os novos, na ordem do chunker (pai antes do filho);
        5. UPDATE final só dos sobreviventes cuja linha mudou (o gatilho `chunks_au` reescreve o
           FTS por linha, então não se atualiza quem não mudou).
        """
        ids = [c.id for c in chunks]
        if len(set(ids)) != len(ids):
            # ids repetidos não deviam existir (o chunker desambigua); o caminho antigo é seguro
            return self._replace_all(doc_id, chunks)

        atuais = {
            r["id"]: r
            for r in self.conn.execute(
                """SELECT id, ordinal, parent_id, kind, symbol, heading_path, start_line,
                          end_line, content, content_hash, token_count
                   FROM chunks WHERE document_id = ?""",
                (doc_id,),
            )
        }
        novos_por_id = {c.id: c for c in chunks}
        removidos = [i for i in atuais if i not in novos_por_id]
        sobreviventes = [c for c in chunks if c.id in atuais]
        adicionados = [c for c in chunks if c.id not in atuais]
        stats = ReplaceStats(kept=len(sobreviventes), added=len(adicionados), removed=len(removidos))

        # 1) o pai vai sair mas o filho fica: solta o filho antes do DELETE
        saindo = set(removidos)
        orfaos = [
            c.id for c in sobreviventes
            if atuais[c.id]["parent_id"] is not None and atuais[c.id]["parent_id"] in saindo
        ]
        if orfaos:
            self.conn.executemany("UPDATE chunks SET parent_id = NULL WHERE id = ?", [(i,) for i in orfaos])
        # 2) removidos
        if removidos:
            self.conn.executemany("DELETE FROM chunks WHERE id = ?", [(i,) for i in removidos])
        # 3) quem muda de ordinal sai do caminho dos outros
        moveram = [c for c in sobreviventes if atuais[c.id]["ordinal"] != c.ordinal]
        if moveram:
            self.conn.executemany(
                "UPDATE chunks SET ordinal = ? WHERE id = ?",
                [(-(atuais[c.id]["ordinal"] + 1), c.id) for c in moveram],
            )
        # 4) novos
        now = utcnow()
        if adicionados:
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
                    for c in adicionados
                ],
            )
        # 5) só o que de fato mudou
        for c in sobreviventes:
            old = atuais[c.id]
            novo = (c.ordinal, c.parent_id, c.kind.value, c.symbol, c.heading_path,
                    c.start_line, c.end_line, c.content, c.content_hash, c.token_count)
            antigo = (old["ordinal"], old["parent_id"], old["kind"], old["symbol"], old["heading_path"],
                      old["start_line"], old["end_line"], old["content"], old["content_hash"],
                      old["token_count"])
            # A comparação usa o estado de ANTES (`atuais`), inclusive o `parent_id` que o
            # passo 1 zerou nos órfãos: o pai antigo saiu, então a linha sempre difere.
            if novo == antigo:
                continue
            self.conn.execute(
                """UPDATE chunks SET ordinal = ?, parent_id = ?, kind = ?, symbol = ?,
                       heading_path = ?, start_line = ?, end_line = ?, content = ?,
                       content_hash = ?, token_count = ? WHERE id = ?""",
                (*novo, c.id),
            )
            stats.updated += 1
            # O prefixo de contexto (`kind`, `symbol`, `heading_path`) entra no texto que foi
            # embutido: se mudou, o vetor ficou velho e o chunk volta para a fila do embedder.
            if (old["symbol"], old["heading_path"], old["kind"]) != (c.symbol, c.heading_path, c.kind.value):
                self.conn.execute("DELETE FROM embeddings WHERE chunk_id = ?", (c.id,))
        return stats

    def _replace_all(self, doc_id: str, chunks: Sequence[Chunk]) -> ReplaceStats:
        """O caminho antigo: apaga tudo e reinsere."""
        antes = int(self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc_id,)
        ).fetchone()[0])
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
        return ReplaceStats(kept=0, added=len(chunks), removed=antes)

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

    def get_by_prefix(self, prefix: str) -> tuple[dict[str, Any] | None, bool]:
        """`(chunk, ambíguo)`. O id completo tem 32 hex; no fio ele vai com 12.

        `prefix` precisa ser hexadecimal (o chamador valida): vira `LIKE 'xxxx%'` sem
        caractere especial. Mais de um chunk com o prefixo é ambiguidade, não escolha.
        """
        rows = self.conn.execute(
            """SELECT c.*, d.rel_path FROM chunks c JOIN documents d ON d.id = c.document_id
               WHERE c.id LIKE ? LIMIT 2""",
            (prefix + "%",),
        ).fetchall()
        if len(rows) > 1:
            return None, True
        return (dict(rows[0]) if rows else None), False

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

    def recent(self, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM index_runs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            )
        ]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM index_runs").fetchone()[0])

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

"""Persistência do grafo. IDs determinísticos, upsert idempotente."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from ragx.core.ids import entity_id, relation_id


class EntityType(StrEnum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"
    ENDPOINT = "endpoint"
    TABLE = "table"
    SERVICE = "service"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"


class RelationType(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    USES = "uses"
    DOCUMENTED_BY = "documented_by"
    MENTIONS = "mentions"
    DEPENDS_ON = "depends_on"


@dataclass(frozen=True, slots=True)
class Entity:
    type: EntityType
    name: str
    qualified_name: str
    document_id: str | None = None
    chunk_id: str | None = None
    summary: str | None = None
    confidence: float = 1.0
    source: str = "structural"

    @property
    def id(self) -> str:
        return entity_id(self.type.value, self.qualified_name)


@dataclass(frozen=True, slots=True)
class Relation:
    src_id: str
    dst_id: str
    type: RelationType
    weight: float = 1.0
    confidence: float = 1.0
    source: str = "structural"
    evidence_chunk_id: str | None = None

    @property
    def id(self) -> str:
        return relation_id(self.src_id, self.type.value, self.dst_id)


# Fronteira entre "lido direto da fonte" e "resolvido por heurística/inferência" —
# mesma distinção que o Graphify chama de EXTRACTED/INFERRED. `structural.py`
# grava confidence=1.0 (hierarquia já está no chunk, sem ambiguidade);
# `reference.py` grava 0.6-0.8 (regex/heurística pode errar). 0.95 separa os
# dois sem depender de o valor exato ser 1.0 (float de ponto flutuante).
_EXTRACTED_THRESHOLD = 0.95


def confidence_tier(confidence: float) -> Literal["extracted", "inferred"]:
    return "extracted" if confidence >= _EXTRACTED_THRESHOLD else "inferred"


@dataclass
class GraphStats:
    entities: int = 0
    relations: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_relation: dict[str, int] = field(default_factory=dict)
    unresolved: int = 0


class GraphStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ── escrita ──────────────────────────────────────────────────────────
    def upsert_entities(self, entities: Iterable[Entity]) -> int:
        rows = [
            (
                e.id, e.type.value, e.name, e.qualified_name, e.document_id,
                e.chunk_id, e.summary, e.confidence, e.source,
            )
            for e in entities
        ]
        if not rows:
            return 0
        self.conn.executemany(
            """INSERT INTO entities
               (id, type, name, qualified_name, document_id, chunk_id, summary,
                confidence, source)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, document_id=excluded.document_id,
                 chunk_id=excluded.chunk_id,
                 summary=COALESCE(excluded.summary, entities.summary),
                 confidence=MAX(excluded.confidence, entities.confidence)""",
            rows,
        )
        return len(rows)

    def upsert_relations(self, relations: Iterable[Relation]) -> int:
        rows = [
            (
                r.id, r.src_id, r.dst_id, r.type.value, r.weight, r.confidence,
                r.source, r.evidence_chunk_id,
            )
            for r in relations
        ]
        if not rows:
            return 0
        self.conn.executemany(
            """INSERT INTO relations
               (id, src_id, dst_id, type, weight, confidence, source, evidence_chunk_id)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 weight=MAX(excluded.weight, relations.weight),
                 confidence=MAX(excluded.confidence, relations.confidence)""",
            rows,
        )
        return len(rows)

    def clear(self, sources: tuple[str, ...] = ("structural", "reference")) -> None:
        """Remove só as camadas indicadas. A camada semântica custa dinheiro e
        é preservada por padrão."""
        ph = ",".join("?" * len(sources))
        self.conn.execute(f"DELETE FROM relations WHERE source IN ({ph})", sources)
        self.conn.execute(f"DELETE FROM entities WHERE source IN ({ph})", sources)

    def prune_orphans(self) -> int:
        cur = self.conn.execute(
            """DELETE FROM relations
               WHERE src_id NOT IN (SELECT id FROM entities)
                  OR dst_id NOT IN (SELECT id FROM entities)"""
        )
        return cur.rowcount or 0

    # ── leitura ──────────────────────────────────────────────────────────
    def stats(self) -> GraphStats:
        s = GraphStats()
        s.entities = int(self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
        s.relations = int(self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0])
        s.by_type = {
            r["type"]: r["n"]
            for r in self.conn.execute(
                "SELECT type, COUNT(*) n FROM entities GROUP BY type ORDER BY n DESC"
            )
        }
        s.by_relation = {
            r["type"]: r["n"]
            for r in self.conn.execute(
                "SELECT type, COUNT(*) n FROM relations GROUP BY type ORDER BY n DESC"
            )
        }
        return s

    def find(
        self, name_or_id: str, entity_type: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM entities WHERE id = ?", (name_or_id,)).fetchone()
        if row:
            return [dict(row)]
        sql = "SELECT * FROM entities WHERE (name = ? COLLATE NOCASE OR qualified_name = ?)"
        args: list[Any] = [name_or_id, name_or_id]
        if entity_type:
            sql += " AND type = ?"
            args.append(entity_type)
        sql += " LIMIT ?"
        args.append(limit)
        exact = [dict(r) for r in self.conn.execute(sql, args)]
        if exact:
            return exact
        sql = "SELECT * FROM entities WHERE name LIKE ? COLLATE NOCASE"
        args = [f"%{name_or_id}%"]
        if entity_type:
            sql += " AND type = ?"
            args.append(entity_type)
        sql += " ORDER BY LENGTH(name) LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args)]

    def list_entities(
        self, entity_type: str | None = None, name: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM entities WHERE 1=1"
        args: list[Any] = []
        if entity_type:
            sql += " AND type = ?"
            args.append(entity_type)
        if name:
            sql += " AND name LIKE ? COLLATE NOCASE"
            args.append(f"%{name}%")
        sql += " ORDER BY type, name LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args)]

    def neighbors(
        self, entity_ids: Iterable[str], relation_types: tuple[str, ...] | None = None
    ) -> list[dict[str, Any]]:
        ids = list(entity_ids)
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        sql = f"""
            SELECT r.*, 'out' AS direction,
                   e.name AS other_name, e.type AS other_type,
                   e.qualified_name AS other_qname, e.id AS other_id
            FROM relations r JOIN entities e ON e.id = r.dst_id
            WHERE r.src_id IN ({ph})
            UNION ALL
            SELECT r.*, 'in' AS direction,
                   e.name AS other_name, e.type AS other_type,
                   e.qualified_name AS other_qname, e.id AS other_id
            FROM relations r JOIN entities e ON e.id = r.src_id
            WHERE r.dst_id IN ({ph})
        """
        args: list[Any] = ids + ids
        rows = [dict(r) for r in self.conn.execute(sql, args)]
        if relation_types:
            rows = [r for r in rows if r["type"] in relation_types]
        return rows

    def degrees(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.conn.execute(
            """SELECT id, (SELECT COUNT(*) FROM relations WHERE src_id = e.id OR dst_id = e.id) AS d
               FROM entities e"""
        ):
            out[r["id"]] = int(r["d"])
        return out

    def chunks_for(self, entity_ids: Iterable[str], limit: int = 3) -> dict[str, list[str]]:
        """Chunks representativos de cada entidade — a ponte grafo → texto."""
        ids = list(entity_ids)
        if not ids:
            return {}
        ph = ",".join("?" * len(ids))
        out: dict[str, list[str]] = {}
        for r in self.conn.execute(
            f"""SELECT e.id AS eid, c.id AS cid FROM entities e
                JOIN chunks c ON c.id = e.chunk_id
                WHERE e.id IN ({ph})""",
            ids,
        ):
            out.setdefault(r["eid"], []).append(r["cid"])
        # entidades sem chunk próprio (arquivo, tecnologia) caem no documento
        for r in self.conn.execute(
            f"""SELECT e.id AS eid, c.id AS cid FROM entities e
                JOIN chunks c ON c.document_id = e.document_id
                WHERE e.id IN ({ph}) AND e.chunk_id IS NULL
                ORDER BY c.ordinal""",
            ids,
        ):
            bucket = out.setdefault(r["eid"], [])
            if len(bucket) < limit:
                bucket.append(r["cid"])
        return out

"""Camada 1 — estrutural. Determinística, custo ~zero, precisão ~100%.

Não re-parseia nada: a hierarquia já está persistida em `chunks`
(kind, symbol, parent_id, document_id). É isso que faz `ragx graph rebuild`
rodar em segundos.

Ver docs/06-grafo.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import PurePosixPath

from ragx.graph.store import Entity, EntityType, Relation, RelationType

_CHUNK_KIND_TO_ENTITY = {
    "class": EntityType.CLASS,
    "function": EntityType.FUNCTION,
    "method": EntityType.METHOD,
}


def extract(conn: sqlite3.Connection) -> tuple[list[Entity], list[Relation], dict[str, str]]:
    """Devolve (entidades, relações, mapa chunk_id -> entity_id)."""
    entities: list[Entity] = []
    relations: list[Relation] = []
    by_chunk: dict[str, str] = {}

    docs = {
        r["id"]: dict(r)
        for r in conn.execute("SELECT id, rel_path, lang, doc_kind, title FROM documents")
    }

    file_entity: dict[str, Entity] = {}
    for doc_id, d in docs.items():
        rel = d["rel_path"]
        ent = Entity(
            type=EntityType.FILE,
            name=PurePosixPath(rel).name,
            qualified_name=rel,
            document_id=doc_id,
            summary=d["title"],
        )
        file_entity[doc_id] = ent
        entities.append(ent)

    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT id, document_id, kind, symbol, parent_id, ordinal
               FROM chunks WHERE symbol IS NOT NULL ORDER BY document_id, ordinal"""
        )
    ]

    # Passo 1: entidades de código, com nome qualificado único por arquivo.
    for c in rows:
        etype = _CHUNK_KIND_TO_ENTITY.get(c["kind"])
        if etype is None:
            continue
        doc = docs.get(c["document_id"])
        if doc is None:
            continue
        symbol = c["symbol"]
        qname = f"{doc['rel_path']}::{symbol}"
        ent = Entity(
            type=etype,
            name=symbol.split(".")[-1],
            qualified_name=qname,
            document_id=c["document_id"],
            chunk_id=c["id"],
        )
        entities.append(ent)
        by_chunk[c["id"]] = ent.id

    # Passo 2: hierarquia. parent_id do chunk já carrega método -> classe.
    for c in rows:
        eid = by_chunk.get(c["id"])
        if eid is None:
            continue
        parent_eid = by_chunk.get(c["parent_id"]) if c["parent_id"] else None
        if parent_eid:
            relations.append(
                Relation(parent_eid, eid, RelationType.CONTAINS, evidence_chunk_id=c["id"])
            )
        else:
            fe = file_entity.get(c["document_id"])
            if fe is not None:
                relations.append(
                    Relation(fe.id, eid, RelationType.CONTAINS, evidence_chunk_id=c["id"])
                )

    return entities, relations, by_chunk

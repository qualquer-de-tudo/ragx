"""Import de pacote `.rag`.

Pacote de terceiro é ENTRADA NÃO CONFIÁVEL: checksums, zip-slip, matriz de
compatibilidade e re-scan de segurança acontecem ANTES de qualquer escrita.

Ver docs/11-export-import.md.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from ragx.config import Config
from ragx.core.errors import RagxError, SecurityBlockedError
from ragx.core.ids import CHUNKER_VERSION, SCHEMA_VERSION
from ragx.core.models import Severity
from ragx.portability.package import CHECKSUMS, MANIFEST, ImportReport
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db, utcnow
from ragx.storage.vectors import register_model

_ALLOWED_PREFIXES = ("knowledge/", "embeddings/", "agents/")


def _safe_name(name: str) -> bool:
    """Zip-slip: entrada com `..` ou caminho absoluto é rejeitada."""
    if name in (MANIFEST, CHECKSUMS):
        return True
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        return False
    if len(name) > 1 and name[1] == ":":
        return False
    return name.startswith(_ALLOWED_PREFIXES)


def verify(path: Path) -> dict[str, Any]:
    """Checksums + nomes de entrada. Levanta antes de qualquer escrita."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        bad = [n for n in names if not _safe_name(n)]
        if bad:
            raise SecurityBlockedError(
                f"pacote com entradas inseguras (zip-slip): {bad[:5]}"
            )
        if MANIFEST not in names:
            raise RagxError("pacote sem manifest.json")
        manifest = json.loads(z.read(MANIFEST).decode("utf-8"))

        if CHECKSUMS in names:
            expected: dict[str, str] = {}
            for line in z.read(CHECKSUMS).decode("utf-8").splitlines():
                if "  " in line:
                    digest, name = line.split("  ", 1)
                    expected[name.strip()] = digest.strip()
            for name, digest in expected.items():
                if name not in names:
                    raise RagxError(f"pacote incompleto: {name} listado mas ausente")
                got = hashlib.sha256(z.read(name)).hexdigest()
                if got != digest:
                    raise SecurityBlockedError(
                        f"checksum divergente em {name}: o pacote foi alterado"
                    )
    return manifest


def compatibility(cfg: Config, manifest: dict[str, Any]) -> tuple[list[str], bool]:
    """Devolve (avisos, aceitar_embeddings)."""
    warnings: list[str] = []
    versions = manifest.get("versions", {})

    if int(manifest.get("schema_version", 1)) > 1:
        raise RagxError(
            f"pacote no schema {manifest['schema_version']}; esta instalação "
            "suporta até 1 — atualize o RAGX"
        )
    if int(versions.get("schema", SCHEMA_VERSION)) > SCHEMA_VERSION:
        raise RagxError("pacote gerado por um RAGX mais novo — atualize antes de importar")

    if str(versions.get("chunker")) != CHUNKER_VERSION:
        warnings.append(
            f"chunker do pacote ({versions.get('chunker')}) difere do local "
            f"({CHUNKER_VERSION}): os ids não vão bater com uma reindexação local"
        )

    accept = True
    model = versions.get("embedding_model")
    # Pergunta ao provider qual é o id dele. Remontar `provider:model` daria
    # uma string que nenhum embedder produz — e todo import descartaria vetores.
    try:
        from ragx.embeddings import build_embedder

        local_id: str | None = build_embedder(cfg).id
    except Exception:
        local_id = None

    if model and local_id and model != local_id:
        warnings.append(
            f"modelo de embedding do pacote ({model}) difere do local; vetores "
            "descartados — a busca semântica exige `ragx index --embed-only`"
        )
        accept = False
    dim = versions.get("versioned_dim")
    if accept and dim and int(dim) != cfg.embedding.versioned_dim:
        warnings.append(
            f"dimensão versionada difere ({dim} vs {cfg.embedding.versioned_dim}); "
            "vetores descartados"
        )
        accept = False

    disabled = manifest.get("security", {}).get("rules_disabled") or []
    if disabled:
        warnings.append(
            f"pacote gerado com {len(disabled)} regra(s) de segurança desabilitada(s): "
            f"{disabled[:5]} — re-scan local é obrigatório"
        )
    return warnings, accept


def import_package(
    cfg: Config, path: Path, mode: str = "replace", skip_embeddings: bool = False
) -> ImportReport:
    report = ImportReport(source=str(path), mode=mode)
    manifest = verify(path)
    report.warnings, accept_vectors = compatibility(cfg, manifest)
    if skip_embeddings:
        accept_vectors = False

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        docs = _read_jsonl(z, "knowledge/documents.jsonl", names)
        chunks = _read_jsonl(z, "knowledge/chunks.jsonl", names)
        entities = _read_json(z, "knowledge/entities.json", names) or []
        relations = _read_json(z, "knowledge/relations.json", names) or []
        vectors = _read_jsonl(z, "embeddings/vectors.jsonl", names) if accept_vectors else []
        model = _read_json(z, "embeddings/model.json", names) if accept_vectors else None

    # Re-scan: o ruleset local pode ser mais estrito que o de origem.
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    blocked = 0
    clean_chunks = []
    for c in chunks:
        findings = gate.scanner.scan_content(c.get("id", "?"), c.get("content", ""))
        if any(f.severity.rank >= Severity.HIGH.rank for f, _v in findings):
            blocked += 1
            continue
        clean_chunks.append(c)
    if blocked:
        report.warnings.append(
            f"{blocked} chunk(s) do pacote bloqueados pelo ruleset local"
        )
    chunks = clean_chunks
    kept_ids = {c["id"] for c in chunks}
    vectors = [v for v in vectors if v.get("chunk_id") in kept_ids]

    # Escrita em transação única.
    now = utcnow()
    with open_db(cfg.db_path) as conn:
        if mode == "replace":
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM entities")

        existing_docs = {r["id"] for r in conn.execute("SELECT id FROM documents")}
        existing_chunks = {r["id"] for r in conn.execute("SELECT id FROM chunks")}

        applied_docs = 0
        for d in docs:
            if mode == "merge" and d["id"] in existing_docs:
                continue  # conflito: o local venceu (foi derivado do código real)
            conn.execute(
                """INSERT OR REPLACE INTO documents
                   (id, rel_path, lang, doc_kind, size_bytes, mtime_ns, content_hash,
                    redacted, title, indexed_at, chunker_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (d["id"], d["rel_path"], d.get("lang"), d["doc_kind"],
                 d.get("size_bytes", 0), d.get("mtime_ns", 0), d["content_hash"],
                 int(d.get("redacted", False)), d.get("title"), now,
                 d.get("chunker_version", CHUNKER_VERSION)),
            )
            applied_docs += 1

        applied_chunks = 0
        for c in chunks:
            if mode == "merge" and c["id"] in existing_chunks:
                continue
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO chunks
                       (id, document_id, ordinal, parent_id, kind, symbol, heading_path,
                        start_line, end_line, content, content_hash, token_count, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], c["document_id"], c["ordinal"], c.get("parent_id"),
                     c["kind"], c.get("symbol"), c.get("heading_path"),
                     c["start_line"], c["end_line"], c["content"], c["content_hash"],
                     c.get("token_count", 0), now),
                )
                applied_chunks += 1
            except Exception:
                continue  # documento ausente por merge: chunk é ignorado

        applied_entities = 0
        for e in entities:
            conn.execute(
                """INSERT OR REPLACE INTO entities
                   (id, type, name, qualified_name, document_id, chunk_id, summary,
                    confidence, source)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (e["id"], e["type"], e["name"], e["qualified_name"],
                 e.get("document_id"), e.get("chunk_id"), e.get("summary"),
                 e.get("confidence", 1.0), e.get("source", "structural")),
            )
            applied_entities += 1

        entity_ids = {r["id"] for r in conn.execute("SELECT id FROM entities")}
        applied_relations = 0
        for r in relations:
            if r["src_id"] not in entity_ids or r["dst_id"] not in entity_ids:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO relations
                   (id, src_id, dst_id, type, weight, confidence, source, evidence_chunk_id)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (r["id"], r["src_id"], r["dst_id"], r["type"], r.get("weight", 1.0),
                 r.get("confidence", 1.0), r.get("source", "structural"),
                 r.get("evidence_chunk_id")),
            )
            applied_relations += 1

        applied_vectors = 0
        if vectors and model:
            register_model(
                conn, model["id"], int(model["dim"]), int(model["versioned_dim"]),
                model.get("quant", "int8"),
            )
            for v in vectors:
                conn.execute(
                    """INSERT OR REPLACE INTO embeddings
                       (chunk_id, model_id, vector, vector_q, q_scale, q_offset, created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (v["chunk_id"], model["id"],
                     bytes.fromhex(v["f32"]) if v.get("f32") else None,
                     bytes.fromhex(v["q"]), v["scale"], v["offset"], now),
                )
                applied_vectors += 1
        conn.commit()

    report.applied = {
        "documents": applied_docs, "chunks": applied_chunks,
        "entities": applied_entities, "relations": applied_relations,
        "embeddings": applied_vectors,
    }
    if not accept_vectors:
        report.skipped["embeddings"] = "modelo/dimensão incompatível ou --skip-embeddings"
    return report


def _read_jsonl(z: zipfile.ZipFile, name: str, names: set[str]) -> list[dict]:
    if name not in names:
        return []
    out = []
    for line in z.read(name).decode("utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _read_json(z: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    return json.loads(z.read(name).decode("utf-8"))

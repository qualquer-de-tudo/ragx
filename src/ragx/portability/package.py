"""Pacote `.rag` — conhecimento portátil.

ZIP (não tar.gz) porque permite ler o `manifest.json` sem descompactar o
arquivo inteiro: `ragx inspect` depende disso.

Duas diferenças deliberadas em relação a `knowledge/`:
  - o pacote INCLUI o conteúdo dos chunks (precisa ser autossuficiente para
    quem não tem o repositório);
  - embeddings viajam em int8 por padrão — `--full-vectors` multiplica por 12.

Ver docs/11-export-import.md.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.core.errors import RagxError, SecurityBlockedError
from ragx.core.ids import CHUNKER_VERSION, SCHEMA_VERSION
from ragx.core.models import Severity
from ragx.security.gate import SecurityGate
from ragx.storage.db import get_meta, open_db, utcnow

MANIFEST = "manifest.json"
CHECKSUMS = "CHECKSUMS.sha256"
PACKAGE_SCHEMA = 1


@dataclass
class ExportReport:
    path: str = ""
    bytes_written: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    integrity: list[str] = field(default_factory=list)
    included_embeddings: bool = False


@dataclass
class ImportReport:
    source: str = ""
    applied: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    mode: str = "replace"


def _remote_hash(root: Path) -> str | None:
    """Hash do remote, NUNCA a URL — ela pode conter token."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=root,
            capture_output=True, text=True, check=True, timeout=5,
        )
    except Exception:
        return None
    url = out.stdout.strip()
    return hashlib.sha256(url.encode()).hexdigest()[:16] if url else None


def _git_commit(root: Path) -> str | None:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root,
            capture_output=True, text=True, check=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


# ── export ──────────────────────────────────────────────────────────────
def export(
    cfg: Config,
    target: Path,
    include_embeddings: bool = True,
    include_agents: bool = False,
    full_vectors: bool = False,
) -> ExportReport:
    report = ExportReport(path=str(target), included_embeddings=include_embeddings)

    with open_db(cfg.db_path, read_only=True) as conn:
        docs = [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY rel_path")]
        chunks = [
            dict(r) for r in conn.execute("SELECT * FROM chunks ORDER BY document_id, ordinal")
        ]
        entities = [dict(r) for r in conn.execute("SELECT * FROM entities ORDER BY id")]
        relations = [dict(r) for r in conn.execute("SELECT * FROM relations ORDER BY id")]
        model = conn.execute(
            "SELECT * FROM embedding_models ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        vectors = []
        if include_embeddings and model is not None:
            vectors = [
                dict(r)
                for r in conn.execute(
                    "SELECT chunk_id, vector, vector_q, q_scale, q_offset FROM embeddings "
                    "WHERE model_id = ? ORDER BY chunk_id",
                    (model["id"],),
                )
            ]
        project_id = get_meta(conn, "project_id", cfg.project.id)

    # [1] Re-scan COMPLETO. Não confia no scan da indexação: o ruleset pode ter
    #     evoluído, e um placeholder pode ter falhado por bug.
    report.findings = _rescan(cfg, docs, chunks, entities)
    blocking = [
        f for f in report.findings
        if Severity(f["severity"]).rank >= Severity.HIGH.rank
    ]
    if blocking:
        raise SecurityBlockedError(
            f"{len(blocking)} achado(s) crítico(s) impedem o export. Nada foi gravado.\n"
            + "\n".join(f"    {f['path']} — {f['rule_id']} (L{f['line']})" for f in blocking[:8])
            + "\n\n  Corrija a origem e reindexe. Não existe --force para isto."
        )

    # [2] Integridade.
    report.integrity = _integrity(docs, chunks, entities, relations, vectors)
    if report.integrity:
        raise RagxError("falha de integridade:\n    " + "\n    ".join(report.integrity))

    # [3] Manifest + [4] pacote.
    report.counts = {
        "documents": len(docs), "chunks": len(chunks), "entities": len(entities),
        "relations": len(relations), "embeddings": len(vectors),
    }
    manifest = {
        "schema_version": PACKAGE_SCHEMA,
        "package_id": hashlib.sha256(
            f"{project_id}{utcnow()}".encode()
        ).hexdigest()[:32],
        "project": {"name": cfg.project.name, "project_id": project_id,
                    "kind": cfg.project.kind},
        "created_at": utcnow(),
        "created_by": "ragx",
        "source": {"git_remote_hash": _remote_hash(cfg.root), "git_commit": _git_commit(cfg.root)},
        "versions": {
            "schema": SCHEMA_VERSION,
            "chunker": CHUNKER_VERSION,
            "ruleset": "builtin@1",
            "embedding_model": model["id"] if model else None,
            "embedding_dim": model["dim"] if model else None,
            "versioned_dim": model["versioned_dim"] if model else None,
            "quant": "float32" if full_vectors else "int8",
        },
        "contents": report.counts,
        "security": {
            "policy": cfg.security.policy,
            "scanned_at": utcnow(),
            "findings": len(report.findings),
            "rules_disabled": sorted(cfg.security.disabled_rules),
        },
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, bytes] = {
        "knowledge/documents.jsonl": _jsonl(
            {
                "id": d["id"], "rel_path": d["rel_path"], "lang": d["lang"],
                "doc_kind": d["doc_kind"], "content_hash": d["content_hash"],
                "title": d["title"], "redacted": bool(d["redacted"]),
                "chunker_version": d["chunker_version"], "size_bytes": d["size_bytes"],
                "mtime_ns": d["mtime_ns"],
            }
            for d in docs
        ),
        # o pacote é autossuficiente: aqui o conteúdo VAI junto
        "knowledge/chunks.jsonl": _jsonl(
            {
                "id": c["id"], "document_id": c["document_id"], "ordinal": c["ordinal"],
                "kind": c["kind"], "symbol": c["symbol"], "heading_path": c["heading_path"],
                "start_line": c["start_line"], "end_line": c["end_line"],
                "content": c["content"], "content_hash": c["content_hash"],
                "token_count": c["token_count"], "parent_id": c["parent_id"],
            }
            for c in chunks
        ),
        "knowledge/entities.json": _json(entities),
        "knowledge/relations.json": _json(relations),
    }

    dictionary = cfg.root / "knowledge" / "dictionary.json"
    if dictionary.is_file():
        payload["knowledge/dictionary.json"] = dictionary.read_bytes()

    federation = cfg.root / "knowledge" / "federation"
    if federation.is_dir():
        for p in sorted(federation.rglob("*")):
            if p.is_file():
                payload[f"knowledge/federation/{p.relative_to(federation).as_posix()}"] = (
                    p.read_bytes()
                )

    if vectors:
        payload["embeddings/model.json"] = _json(
            {
                "id": model["id"], "dim": model["dim"],
                "versioned_dim": model["versioned_dim"], "quant": model["quant"],
                "full_vectors": full_vectors,
            }
        )
        payload["embeddings/vectors.jsonl"] = _jsonl(
            {
                "chunk_id": v["chunk_id"],
                "q": v["vector_q"].hex(),
                "scale": v["q_scale"],
                "offset": v["q_offset"],
                **({"f32": v["vector"].hex()} if full_vectors and v["vector"] else {}),
            }
            for v in vectors
        )

    if include_agents:
        agents = cfg.root / "agents"
        if agents.is_dir():
            for p in sorted(agents.rglob("*")):
                if p.is_file():
                    payload[f"agents/{p.relative_to(agents).as_posix()}"] = p.read_bytes()

    checksums = "".join(
        f"{hashlib.sha256(body).hexdigest()}  {name}\n"
        for name, body in sorted(payload.items())
    )
    manifest_body = _json(manifest)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, manifest_body)  # primeiro: `inspect` lê sem expandir
        for name, body in sorted(payload.items()):
            z.writestr(name, body)
        z.writestr(CHECKSUMS, checksums)

    report.bytes_written = target.stat().st_size
    return report


def _jsonl(rows: Any) -> bytes:
    return "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows
    ).encode("utf-8")


def _json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _rescan(cfg: Config, docs: list[dict], chunks: list[dict], entities: list[dict]) -> list[dict]:
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    findings: list[dict[str, Any]] = []
    by_doc = {d["id"]: d["rel_path"] for d in docs}
    for c in chunks:
        rel = by_doc.get(c["document_id"], "?")
        for f, _value in gate.scanner.scan_content(rel, c["content"]):
            findings.append(
                {"path": rel, "rule_id": f.rule_id, "severity": f.severity.value,
                 "line": c["start_line"] + f.line - 1, "preview": f.preview}
            )
    for e in entities:
        blob = f"{e['name']} {e['qualified_name']} {e['summary'] or ''}"
        for f, _v in gate.scanner.scan_content("entities", blob):
            findings.append(
                {"path": f"entity:{e['type']}", "rule_id": f.rule_id,
                 "severity": f.severity.value, "line": 0, "preview": f.preview}
            )
    return findings


def _integrity(
    docs: list[dict], chunks: list[dict], entities: list[dict],
    relations: list[dict], vectors: list[dict],
) -> list[str]:
    problems: list[str] = []
    doc_ids = {d["id"] for d in docs}
    chunk_ids = {c["id"] for c in chunks}
    entity_ids = {e["id"] for e in entities}

    orphan_chunks = [c["id"] for c in chunks if c["document_id"] not in doc_ids]
    if orphan_chunks:
        problems.append(f"{len(orphan_chunks)} chunk(s) sem documento")
    orphan_vectors = [v["chunk_id"] for v in vectors if v["chunk_id"] not in chunk_ids]
    if orphan_vectors:
        problems.append(f"{len(orphan_vectors)} embedding(s) sem chunk")
    orphan_rel = [
        r["id"] for r in relations
        if r["src_id"] not in entity_ids or r["dst_id"] not in entity_ids
    ]
    if orphan_rel:
        problems.append(f"{len(orphan_rel)} relação(ões) sem entidade")
    for d in docs:
        if Path(d["rel_path"]).is_absolute() or d["rel_path"].startswith("/"):
            problems.append(f"caminho absoluto no pacote: {d['rel_path']}")
            break
    return problems


# ── inspect ─────────────────────────────────────────────────────────────
def inspect(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read(MANIFEST).decode("utf-8"))

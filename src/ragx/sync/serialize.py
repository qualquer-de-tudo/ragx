"""Serialização de `knowledge/` — texto estável, diffável, dentro do orçamento.

Duas decisões governam este módulo (ADR-0010):

  1. `chunks/*.jsonl` NÃO carrega `content`. É redundante: já está no
     repositório, no caminho e nas linhas registradas.
  2. embeddings vão em int8@versioned_dim, shardados por PREFIXO DO ID — é o que
     mantém 15 de 16 shards byte-idênticos quando um chunk muda.

Ver docs/12-git-sync.md e docs/16-orcamento-de-tamanho.md.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path

from ragx.base import source as base_source
from ragx.config import Config
from ragx.core.ids import CHUNKER_VERSION, SCHEMA_VERSION, shard_of
from ragx.sizing.budget import Budget
from ragx.storage.db import get_meta, open_db, utcnow

MANIFEST = "manifest.json"
BASE_MANIFEST = "base.json"
_SEP = "__"
_SHARD_MAGIC = b"RAGXI8\x00\x01"


@dataclass
class SerializeReport:
    documents: int = 0
    chunks: int = 0
    embeddings: int = 0
    entities: int = 0
    relations: int = 0
    shards: int = 0
    bytes_written: int = 0
    files_written: int = 0
    removed: int = 0
    warnings: list[str] = field(default_factory=list)


def artifact_name(rel_path: str) -> str:
    """`src/a/b.py` -> `src__a__b.py`. Colisão real recebe sufixo de hash."""
    flat = rel_path.replace("/", _SEP)
    if _SEP in rel_path:  # o caminho já continha '__': desambigua
        import hashlib

        flat = f"{flat}-{hashlib.sha256(rel_path.encode()).hexdigest()[:6]}"
    return flat


def _dump_json(path: Path, data: object) -> int:
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return len(body.encode("utf-8"))


def _dump_jsonl(path: Path, rows: list[dict]) -> int:
    body = "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return len(body.encode("utf-8"))


def serialize(cfg: Config, out_dir: str = "knowledge") -> SerializeReport:
    report = SerializeReport()
    target = cfg.root / out_dir
    target.mkdir(parents=True, exist_ok=True)

    with open_db(cfg.db_path, read_only=True) as conn:
        # Conhecimento base NÃO é versionado: ele não existe no working tree,
        # então não pode ser reidratado (ADR-0010), e duplicá-lo em cada
        # repositório queimaria o orçamento do Git à toa. O que vai para o Git é
        # o REGISTRO das fontes — `ragx base sync` reconstrói a base idêntica.
        docs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM documents WHERE rel_path NOT LIKE ? ORDER BY rel_path",
                (f"{base_source.PREFIX}/%",),
            )
        ]
        n_chunks = int(
            conn.execute(
                """SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id
                   WHERE d.rel_path NOT LIKE ?""",
                (f"{base_source.PREFIX}/%",),
            ).fetchone()[0]
        )

        # Orçamento é restrição, não aviso: recusa ANTES de escrever.
        Budget(cfg).enforce(n_chunks, cfg.embedding.versioned_dim)

        report.bytes_written += _write_documents(conn, target, docs, report)
        report.bytes_written += _write_chunks(conn, target, docs, report)
        report.bytes_written += _write_embeddings(conn, target, cfg, report)
        report.bytes_written += _write_graph(conn, target, report)
        report.bytes_written += _write_base(cfg, target, report)
        report.bytes_written += _write_manifest(conn, target, cfg, report)

    report.files_written = sum(1 for p in target.rglob("*") if p.is_file())
    _check_artifacts(cfg, target, report)
    return report


def _write_documents(
    conn: sqlite3.Connection, target: Path, docs: list[dict], report: SerializeReport
) -> int:
    folder = target / "documents"
    written = 0
    keep: set[str] = set()
    for d in docs:
        name = f"{artifact_name(d['rel_path'])}.json"
        keep.add(name)
        written += _dump_json(
            folder / name,
            {
                "id": d["id"], "rel_path": d["rel_path"], "lang": d["lang"],
                "doc_kind": d["doc_kind"], "content_hash": d["content_hash"],
                "size_bytes": d["size_bytes"], "title": d["title"],
                "redacted": bool(d["redacted"]), "chunker_version": d["chunker_version"],
            },
        )
        report.documents += 1
    report.removed += _prune(folder, keep)
    return written


def _write_chunks(
    conn: sqlite3.Connection, target: Path, docs: list[dict], report: SerializeReport
) -> int:
    folder = target / "chunks"
    written = 0
    keep: set[str] = set()
    for d in docs:
        rows = [
            {
                "id": c["id"], "ordinal": c["ordinal"], "kind": c["kind"],
                "symbol": c["symbol"], "heading_path": c["heading_path"],
                "lines": [c["start_line"], c["end_line"]],
                "content_hash": c["content_hash"], "tokens": c["token_count"],
                "parent": c["parent_id"],
                # SEM "content": reidratado do working tree (ADR-0010)
            }
            for c in conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal", (d["id"],)
            )
        ]
        if not rows:
            continue
        name = f"{artifact_name(d['rel_path'])}.jsonl"
        keep.add(name)
        written += _dump_jsonl(folder / name, rows)
        report.chunks += len(rows)
    report.removed += _prune(folder, keep)
    return written


def _write_embeddings(
    conn: sqlite3.Connection, target: Path, cfg: Config, report: SerializeReport
) -> int:
    folder = target / "embeddings"
    model = conn.execute(
        "SELECT * FROM embedding_models ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if model is None or cfg.embedding.versioned_dim <= 0:
        report.removed += _prune(folder, set())
        return 0

    shards = cfg.size.shards
    buckets: dict[str, list[tuple[str, bytes, float, float]]] = {
        f"{i:02x}": [] for i in range(shards)
    }
    for r in conn.execute(
        """SELECT e.chunk_id, e.vector_q, e.q_scale, e.q_offset
           FROM embeddings e
           JOIN chunks c ON c.id = e.chunk_id
           JOIN documents d ON d.id = c.document_id
           WHERE e.model_id = ? AND d.rel_path NOT LIKE ?""",
        (model["id"], f"{base_source.PREFIX}/%"),
    ):
        buckets[shard_of(r["chunk_id"], shards)].append(
            (r["chunk_id"], r["vector_q"], r["q_scale"], r["q_offset"])
        )
        report.embeddings += 1

    written = 0
    keep = {MANIFEST}
    dim = int(model["versioned_dim"])
    for name, items in buckets.items():
        fname = f"shard-{name}.i8"
        keep.add(fname)
        items.sort(key=lambda t: t[0])  # ordem estável -> diff estável
        blob = bytearray(_SHARD_MAGIC)
        blob += struct.pack("<II", dim, len(items))
        for chunk_id, vec, scale, offset in items:
            blob += bytes.fromhex(chunk_id)
            blob += struct.pack("<ff", float(scale), float(offset))
            blob += vec[:dim].ljust(dim, b"\x00")
        path = folder / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(blob))
        written += len(blob)
        report.shards += 1

    written += _dump_json(
        folder / MANIFEST,
        {
            "model": model["id"], "dim": model["dim"], "versioned_dim": dim,
            "quant": model["quant"], "shards": shards, "count": report.embeddings,
        },
    )
    report.removed += _prune(folder, keep)
    return written


def _write_graph(
    conn: sqlite3.Connection, target: Path, report: SerializeReport
) -> int:
    written = 0
    # Entidades vindas do conhecimento base ficam fora do Git pelo mesmo motivo
    # que os documentos — e junto com elas as relações que as tocam, senão o
    # artefato versionado apontaria para nós inexistentes.
    base_ent = (
        "SELECT e.id FROM entities e JOIN documents d ON d.id = e.document_id "
        "WHERE d.rel_path LIKE :base"
    )
    for kind, sql, cols in (
        ("entities",
         f"SELECT * FROM entities WHERE id NOT IN ({base_ent}) ORDER BY id",
         ("id", "type", "name", "qualified_name", "document_id", "chunk_id",
          "summary", "confidence", "source")),
        ("relations",
         f"SELECT * FROM relations WHERE src_id NOT IN ({base_ent}) "
         f"AND dst_id NOT IN ({base_ent}) ORDER BY id",
         ("id", "src_id", "dst_id", "type", "weight", "confidence", "source",
          "evidence_chunk_id")),
    ):
        folder = target / kind
        buckets: dict[str, list[dict]] = {f"{i:02x}": [] for i in range(16)}
        n = 0
        for r in conn.execute(sql, {"base": f"{base_source.PREFIX}/%"}):
            buckets[shard_of(r["id"], 16)].append({c: r[c] for c in cols})
            n += 1
        keep = set()
        for name, rows in buckets.items():
            fname = f"shard-{name}.json"
            keep.add(fname)
            rows.sort(key=lambda x: x["id"])
            written += _dump_json(folder / fname, rows)
        report.removed += _prune(folder, keep)
        setattr(report, kind, n)
    return written


def _write_base(cfg: Config, target: Path, report: SerializeReport) -> int:
    """`knowledge/base.json` — a receita, não o conteúdo.

    Poucas centenas de bytes que permitem a qualquer clone do repositório
    reconstruir exatamente a mesma base com `ragx base sync`, incluindo o commit
    exato de cada fonte.
    """
    path = target / BASE_MANIFEST
    fontes = [
        {"name": s.name, "origin": s.origin, "kind": s.kind, "ref": s.ref,
         "commit": s.commit}
        for s in base_source.load_registry(cfg)
        if s.enabled and s.kind == "git"
    ]
    declaradas = [o for o in cfg.base.sources if o]
    if not fontes and not declaradas:
        if path.is_file():
            path.unlink()
            report.removed += 1
        return 0
    return _dump_json(path, {"schema_version": 1, "required": declaradas, "sources": fontes})


def _write_manifest(
    conn: sqlite3.Connection, target: Path, cfg: Config, report: SerializeReport
) -> int:
    return _dump_json(
        target / MANIFEST,
        {
            "schema_version": SCHEMA_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "project": {
                "id": get_meta(conn, "project_id", cfg.project.id),
                "name": cfg.project.name,
                "kind": cfg.project.kind,
            },
            "counts": {
                "documents": report.documents, "chunks": report.chunks,
                "embeddings": report.embeddings, "entities": report.entities,
                "relations": report.relations,
            },
            "generated_at": utcnow(),
        },
    )


def _prune(folder: Path, keep: set[str]) -> int:
    """Artefato de documento que sumiu precisa sumir do Git também."""
    if not folder.is_dir():
        return 0
    removed = 0
    for p in folder.iterdir():
        if p.is_file() and p.name not in keep:
            p.unlink()
            removed += 1
    return removed


def _check_artifacts(cfg: Config, target: Path, report: SerializeReport) -> None:
    limit = cfg.size.max_artifact_bytes
    for p in target.rglob("*"):
        if p.is_file() and p.stat().st_size > limit:
            report.warnings.append(
                f"{p.relative_to(target).as_posix()} passa de max_artifact_bytes "
                f"({limit} bytes) — aumente [size] shards"
            )


# ── leitura ─────────────────────────────────────────────────────────────
def read_manifest(cfg: Config, out_dir: str = "knowledge") -> dict | None:
    path = cfg.root / out_dir / MANIFEST
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_documents(cfg: Config, out_dir: str = "knowledge") -> list[dict]:
    folder = cfg.root / out_dir / "documents"
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def read_chunks(cfg: Config, rel_path: str, out_dir: str = "knowledge") -> list[dict]:
    path = cfg.root / out_dir / "chunks" / f"{artifact_name(rel_path)}.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_embeddings(cfg: Config, out_dir: str = "knowledge") -> dict[str, tuple[bytes, float, float]]:
    folder = cfg.root / out_dir / "embeddings"
    manifest = folder / MANIFEST
    if not manifest.is_file():
        return {}
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    dim = int(meta["versioned_dim"])
    out: dict[str, tuple[bytes, float, float]] = {}
    for p in sorted(folder.glob("shard-*.i8")):
        blob = p.read_bytes()
        if not blob.startswith(_SHARD_MAGIC):
            continue
        pos = len(_SHARD_MAGIC)
        _d, count = struct.unpack_from("<II", blob, pos)
        pos += 8
        entry = 16 + 8 + dim
        for _ in range(count):
            chunk_id = blob[pos : pos + 16].hex()
            scale, offset = struct.unpack_from("<ff", blob, pos + 16)
            vec = blob[pos + 24 : pos + 24 + dim]
            out[chunk_id] = (vec, scale, offset)
            pos += entry
    return out

"""Hub local — agrega N projetos na máquina do dev.

Regra dura (ADR-0009): o hub NUNCA lê o filesystem de projeto nenhum. Ele lê
apenas artefatos DERIVADOS (`knowledge/`, `federation/`), que já passaram pelo
gate do projeto de origem — e os re-escaneia na entrada, porque o ruleset local
pode ser mais estrito.

Ver docs/17-multiprojeto-e-federacao.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ragx.config import Config, load_config
from ragx.core.errors import RagxError, UsageError
from ragx.federation import slice as fed_slice
from ragx.security.gate import SecurityGate
from ragx.storage.db import utcnow

HUB_MIGRATIONS = Path(__file__).resolve().parents[1] / "storage" / "migrations" / "hub"
REGISTRY = "registry.json"


@dataclass
class ProjectRef:
    id: str
    name: str
    path: str | None = None
    cloned: bool = False
    remote_hash: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = None
    versioned_dim: int | None = None
    visibility: str = "workspace"
    status: str = "ok"
    chunks: int = 0
    last_sync: str | None = None
    manifest_hash: str | None = None


@dataclass
class HubSyncReport:
    synced: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    items: int = 0
    redacted: int = 0
    warnings: list[str] = field(default_factory=list)


def hub_dir(cfg: Config) -> Path:
    return cfg.hub_dir


def hub_db(cfg: Config) -> Path:
    return hub_dir(cfg) / "hub.db"


def open_hub(cfg: Config, read_only: bool = False) -> sqlite3.Connection:
    path = hub_db(cfg)
    if read_only and not path.exists():
        raise RagxError("hub vazio — registre um projeto com `ragx project register`")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro" if read_only else path, uri=read_only)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not read_only:
        _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    for f in sorted(HUB_MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = int(f.name[:4])
        if version <= current:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()


# ── registro ────────────────────────────────────────────────────────────
def register(
    cfg: Config, path: Path | None = None, name: str | None = None,
    from_federation: Path | None = None, visibility: str | None = None,
) -> ProjectRef:
    if from_federation is not None:
        return _register_federation_only(cfg, from_federation, name)
    if path is None:
        raise UsageError("informe um caminho ou --from-federation")

    target = Path(path).resolve()
    if not (target / "ragx.toml").is_file():
        raise UsageError(f"{target} não é um projeto RAGX (falta ragx.toml)")

    other = load_config(target)
    vis = visibility or other.project.visibility
    if vis == "private":
        raise UsageError(
            f"{other.project.name} está marcado como `private` e não pode entrar no hub"
        )

    ref = ProjectRef(
        id=other.project.id or hashlib.sha256(str(target).encode()).hexdigest()[:12],
        name=name or other.project.name,
        path=str(target),
        cloned=True,
        embedding_model=other.embedding.model,
        embedding_dim=other.embedding.dim,
        versioned_dim=other.embedding.versioned_dim,
        visibility=vis,
    )
    _upsert(cfg, ref)
    return ref


def _register_federation_only(cfg: Config, source: Path, name: str | None) -> ProjectRef:
    """Projeto NÃO clonado: entra só com os contratos. O caso comum de
    microsserviços mantidos por outro time."""
    data = fed_slice.load(source)
    service = data.get("service", {})
    if not service.get("name"):
        raise UsageError(f"fatia inválida (sem service.name): {source}")

    ref = ProjectRef(
        id=service.get("project_id") or hashlib.sha256(
            service["name"].encode()
        ).hexdigest()[:12],
        name=name or service["name"],
        path=None,
        cloned=False,
        remote_hash=service.get("remote_hash"),
        visibility="workspace",
    )
    _upsert(cfg, ref)
    stored = hub_dir(cfg) / "federation" / ref.name
    stored.mkdir(parents=True, exist_ok=True)
    (stored / "slice.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return ref


def _upsert(cfg: Config, ref: ProjectRef) -> None:
    conn = open_hub(cfg)
    try:
        conn.execute(
            """INSERT INTO projects
               (id, name, path, cloned, remote_hash, embedding_model, embedding_dim,
                versioned_dim, visibility, status, chunks, last_sync, manifest_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, path=excluded.path, cloned=excluded.cloned,
                 remote_hash=excluded.remote_hash,
                 embedding_model=excluded.embedding_model,
                 embedding_dim=excluded.embedding_dim,
                 versioned_dim=excluded.versioned_dim,
                 visibility=excluded.visibility""",
            (ref.id, ref.name, ref.path, int(ref.cloned), ref.remote_hash,
             ref.embedding_model, ref.embedding_dim, ref.versioned_dim,
             ref.visibility, ref.status, ref.chunks, ref.last_sync, ref.manifest_hash),
        )
        conn.commit()
    finally:
        conn.close()
    _write_registry(cfg)


def unregister(cfg: Config, name: str) -> bool:
    conn = open_hub(cfg)
    try:
        cur = conn.execute("DELETE FROM projects WHERE name = ?", (name,))
        conn.commit()
        removed = (cur.rowcount or 0) > 0
    finally:
        conn.close()
    _write_registry(cfg)
    return removed


def list_projects(cfg: Config) -> list[dict[str, Any]]:
    if not hub_db(cfg).exists():
        return []
    conn = open_hub(cfg, read_only=True)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY name")]
    finally:
        conn.close()


def _write_registry(cfg: Config) -> None:
    path = hub_dir(cfg) / REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": 1, "projects": list_projects(cfg)},
            ensure_ascii=False, indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8", newline="\n",
    )


# ── sync ────────────────────────────────────────────────────────────────
def sync(cfg: Config, only: str | None = None) -> HubSyncReport:
    report = HubSyncReport()
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    conn = open_hub(cfg)
    try:
        for row in conn.execute("SELECT * FROM projects ORDER BY name"):
            ref = dict(row)
            if only and ref["name"] != only:
                continue
            if ref["visibility"] == "private":
                report.skipped[ref["name"]] = "private"
                continue

            data, status, why = _load_slice(cfg, ref)
            if data is None:
                conn.execute(
                    "UPDATE projects SET status = ? WHERE id = ?", (status, ref["id"])
                )
                report.skipped[ref["name"]] = why
                continue

            digest = hashlib.sha256(
                json.dumps(data, sort_keys=True).encode()
            ).hexdigest()[:16]
            if digest == ref["manifest_hash"] and not only:
                report.skipped[ref["name"]] = "sem mudanças"
                continue

            n, redacted = _ingest(conn, ref["id"], data, gate)
            report.items += n
            report.redacted += redacted
            report.synced.append(ref["name"])
            conn.execute(
                "UPDATE projects SET status='ok', last_sync=?, manifest_hash=? WHERE id=?",
                (utcnow(), digest, ref["id"]),
            )
        conn.commit()
        _check_models(conn, report)
    finally:
        conn.close()
    _write_registry(cfg)
    return report


def _load_slice(cfg: Config, ref: dict) -> tuple[dict | None, str, str]:
    """Lê SÓ artefatos derivados. Nunca o código-fonte do outro projeto."""
    if ref["cloned"] and ref["path"]:
        root = Path(ref["path"])
        if not root.is_dir():
            return None, "missing", "caminho registrado não existe mais"
        folder = root / "knowledge" / fed_slice.FOLDER
        if not folder.is_dir():
            return None, "stale", "sem fatia de federação (rode `ragx federation build` lá)"
        return fed_slice.load(folder), "ok", ""

    stored = hub_dir(cfg) / "federation" / ref["name"] / "slice.json"
    if not stored.is_file():
        return None, "missing", "fatia avulsa ausente"
    return fed_slice.load(stored), "ok", ""


def _ingest(
    conn: sqlite3.Connection, project_id: str, data: dict, gate: SecurityGate
) -> tuple[int, int]:
    conn.execute("DELETE FROM federation_items WHERE project_id = ?", (project_id,))
    contracts = data.get("contracts", {}) or {}
    n = redacted = 0
    for direction in ("provides", "consumes"):
        for kind, entries in (data.get(direction) or {}).items():
            for e in entries or []:
                blob = " ".join(str(v) for v in e.values() if v)
                # Re-scan na entrada: o ruleset local pode ser mais estrito.
                if gate.scanner.scan_content("hub", blob):
                    redacted += 1
                    continue
                body = None
                if e.get("contract"):
                    key = str(e["contract"]).replace("/", "__")
                    body = contracts.get(key)
                item_id = hashlib.sha256(
                    f"{direction}{kind}{e['normalized']}".encode()
                ).hexdigest()[:32]
                conn.execute(
                    """INSERT OR REPLACE INTO federation_items
                       (id, project_id, direction, kind, normalized, raw, handler,
                        contract_body, source_ref, confidence)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (item_id, project_id, direction, kind, e["normalized"], e.get("raw", ""),
                     e.get("handler"), body, e.get("source", "?"),
                     float(e.get("confidence", 1.0))),
                )
                n += 1
    return n, redacted


def _check_models(conn: sqlite3.Connection, report: HubSyncReport) -> None:
    """Vetores de modelos distintos NÃO são comparáveis: comparar produziria
    ranking aleatório com aparência de resultado."""
    models = {
        r["embedding_model"]
        for r in conn.execute(
            "SELECT DISTINCT embedding_model FROM projects WHERE cloned = 1"
        )
        if r["embedding_model"]
    }
    if len(models) > 1:
        conn.execute(
            "UPDATE projects SET status = 'degraded' WHERE cloned = 1 "
            "AND embedding_model != (SELECT embedding_model FROM projects "
            "WHERE cloned = 1 ORDER BY last_sync DESC LIMIT 1)"
        )
        report.warnings.append(
            f"modelos de embedding divergentes entre projetos ({sorted(models)}): "
            "os divergentes participam só por keyword e federação"
        )


def status(cfg: Config) -> dict[str, Any]:
    projects = list_projects(cfg)
    if not projects:
        return {"projects": [], "links": 0, "unresolved": 0, "items": 0}
    conn = open_hub(cfg, read_only=True)
    try:
        return {
            "projects": projects,
            "items": int(conn.execute("SELECT COUNT(*) FROM federation_items").fetchone()[0]),
            "links": int(conn.execute("SELECT COUNT(*) FROM cross_links").fetchone()[0]),
            "unresolved": int(conn.execute("SELECT COUNT(*) FROM unresolved").fetchone()[0]),
        }
    finally:
        conn.close()


def reset(cfg: Config) -> None:
    import shutil

    if hub_dir(cfg).is_dir():
        shutil.rmtree(hub_dir(cfg))

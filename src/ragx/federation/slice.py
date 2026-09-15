"""Fatia de federação — a superfície pública, versionada e AUTOSSUFICIENTE.

Ao contrário de `knowledge/`, a fatia carrega os contratos POR VALOR: é o que
permite outro projeto usar `POST /api/payments` sem ter este repositório clonado.
Cabe em poucos KB porque contém só a superfície, nunca a implementação.

Ver docs/17-multiprojeto-e-federacao.md e ADR-0011.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.core.errors import RagxError
from ragx.federation.surface import SurfaceItem, extract, persist
from ragx.security.gate import SecurityGate
from ragx.storage.db import get_meta, open_db, utcnow

SCHEMA = 1
FOLDER = "federation"
_MAX_CONTRACT_BYTES = 64 * 1024


@dataclass
class SliceReport:
    path: str = ""
    provides: int = 0
    consumes: int = 0
    contracts: int = 0
    bytes_written: int = 0
    redacted: int = 0
    skipped_private: bool = False
    warnings: list[str] = field(default_factory=list)


def build(cfg: Config, out_dir: str = "knowledge") -> SliceReport:
    report = SliceReport()

    if cfg.project.visibility == "private":
        # Projeto privado não publica nada, nem para o hub local.
        report.skipped_private = True
        _remove(cfg, out_dir)
        return report

    with open_db(cfg.db_path) as conn:
        items = extract(conn, cfg.root)
        persist(conn, items)
        conn.commit()
        project_id = get_meta(conn, "project_id", cfg.project.id)
        languages = sorted(
            {r["lang"] for r in conn.execute("SELECT DISTINCT lang FROM documents") if r["lang"]}
        )

    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    provides = [i for i in items if i.direction == "provides"]
    consumes = [i for i in items if i.direction == "consumes"]

    target = cfg.root / out_dir / FOLDER
    target.mkdir(parents=True, exist_ok=True)

    service = {
        "schema_version": SCHEMA,
        "project_id": project_id,
        "name": cfg.project.name,
        "kind": cfg.project.kind,
        "languages": languages,
        "remote_hash": _remote_hash(cfg.root),
        "generated_at": utcnow(),
    }
    report.bytes_written += _write(target / "service.json", service)
    report.bytes_written += _write(target / "provides.json", _group(provides, gate, report))
    report.bytes_written += _write(target / "consumes.json", _group(consumes, gate, report))

    report.contracts = _copy_contracts(cfg, target, provides, gate, report)
    report.bytes_written += _write(target / "glossary.json", _glossary(cfg))

    report.provides = len(provides)
    report.consumes = len(consumes)
    report.path = str(target)

    if report.bytes_written > 1_048_576:
        report.warnings.append(
            f"fatia de federação com {report.bytes_written / 1024:.0f} KB — "
            "ela deve conter só a superfície, não a implementação"
        )
    return report


def _group(
    items: list[SurfaceItem], gate: SecurityGate, report: SliceReport
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"http": [], "event": [], "package": [], "table": []}
    for i in items:
        entry = {
            "normalized": i.normalized,
            "raw": i.raw,
            "handler": i.handler,
            "contract": i.contract,
            "source": i.source_ref,
            "confidence": round(i.confidence, 2),
            "detected_by": i.detected_by,
        }
        if _has_secret(gate, entry):
            report.redacted += 1
            continue
        out.setdefault(i.kind, []).append(entry)
    for k in out:
        out[k].sort(key=lambda e: e["normalized"])
    return out


def _has_secret(gate: SecurityGate, entry: dict[str, Any]) -> bool:
    """A fatia é artefato COMPARTILHADO: re-scan antes de gravar."""
    blob = " ".join(str(v) for v in entry.values() if v)
    return bool(gate.scanner.scan_content("federation", blob))


def _copy_contracts(
    cfg: Config, target: Path, provides: list[SurfaceItem],
    gate: SecurityGate, report: SliceReport,
) -> int:
    """Contratos vão POR VALOR: sem isso a fatia não é autossuficiente."""
    folder = target / "contracts"
    wanted = {i.contract for i in provides if i.contract}
    if not wanted:
        if folder.is_dir():
            for p in folder.iterdir():
                p.unlink()
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    copied = 0
    for rel in sorted(wanted):
        src = cfg.root / str(rel)
        if not src.is_file() or src.stat().st_size > _MAX_CONTRACT_BYTES:
            continue
        raw = src.read_bytes()
        decision = gate.admit(str(rel), raw)
        if not decision.admitted or decision.content is None:
            report.warnings.append(f"contrato {rel} bloqueado pelo gate")
            continue
        name = str(rel).replace("/", "__")
        (folder / name).write_text(decision.content, encoding="utf-8", newline="\n")
        copied += 1
    return copied


def _glossary(cfg: Config) -> list[dict[str, Any]]:
    from ragx.dictionary import builder

    data = builder.load(cfg)
    return (data or {}).get("glossary", [])[:30]


def _write(path: Path, data: Any) -> int:
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return len(body.encode("utf-8"))


def _remote_hash(root: Path) -> str | None:
    import hashlib
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


def _remove(cfg: Config, out_dir: str) -> None:
    import shutil

    target = cfg.root / out_dir / FOLDER
    if target.is_dir():
        shutil.rmtree(target)


# ── leitura / export avulso ─────────────────────────────────────────────
def load(path: Path) -> dict[str, Any]:
    """Lê uma fatia de disco (pasta) ou de um `.fed.json`."""
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if not path.is_dir():
        raise RagxError(f"fatia de federação não encontrada: {path}")
    out: dict[str, Any] = {}
    for name in ("service", "provides", "consumes", "glossary"):
        f = path / f"{name}.json"
        out[name] = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    contracts: dict[str, str] = {}
    folder = path / "contracts"
    if folder.is_dir():
        for p in sorted(folder.iterdir()):
            if p.is_file():
                contracts[p.name] = p.read_text(encoding="utf-8", errors="replace")
    out["contracts"] = contracts
    return out


def export_file(cfg: Config, target: Path, out_dir: str = "knowledge") -> int:
    """Fatia avulsa: 'meu time não te dá acesso ao repo, mas aqui está o contrato'."""
    data = load(cfg.root / out_dir / FOLDER)
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    return len(body.encode("utf-8"))

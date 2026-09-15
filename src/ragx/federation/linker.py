"""Resolução de vínculos: cruza `consumes` de um projeto com `provides` dos outros.

Consumo sem provedor e divergência de método são os achados mais úteis da
federação — a federação encontra erro de integração que nenhum dos dois
repositórios enxerga sozinho. Por isso `unresolved` é tabela de primeira
classe, não log.

Ver docs/17-multiprojeto-e-federacao.md.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ragx.config import Config
from ragx.federation.hub import open_hub
from ragx.storage.db import utcnow

# Escala de confiança por tipo de evidência (docs/17).
CONF_CONTRACT = 1.0
CONF_METHOD_PATH = 0.95
CONF_NAME = 0.8
CONF_METHOD_MISMATCH = 0.6
CONF_SIMILAR_NAME = 0.4  # vira sugestão, NÃO aresta

_RELATION = {"http": "consumes", "package": "depends_on", "table": "depends_on"}


@dataclass
class Link:
    src_project: str
    dst_project: str
    kind: str
    normalized: str
    relation: str
    confidence: float
    evidence: str

    @property
    def id(self) -> str:
        return hashlib.sha256(
            f"{self.src_project}{self.dst_project}{self.kind}{self.normalized}".encode()
        ).hexdigest()[:32]


@dataclass
class LinkReport:
    links: list[Link] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    divergences: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)


def link(cfg: Config) -> LinkReport:
    report = LinkReport()
    conn = open_hub(cfg)
    try:
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM projects")}
        provides: dict[tuple[str, str], list[dict]] = defaultdict(list)
        consumes: list[dict] = []
        for r in conn.execute("SELECT * FROM federation_items"):
            item = dict(r)
            if item["direction"] == "provides":
                provides[(item["kind"], item["normalized"])].append(item)
            else:
                consumes.append(item)

        # Índice por rota SEM o método: permite detectar divergência de verbo.
        by_route: dict[str, list[dict]] = defaultdict(list)
        for (kind, normalized), items in provides.items():
            if kind == "http" and " " in normalized:
                by_route[normalized.split(" ", 1)[1]].extend(items)

        conn.execute("DELETE FROM cross_links")
        conn.execute("DELETE FROM unresolved")
        now = utcnow()

        for c in consumes:
            key = (c["kind"], c["normalized"])
            matches = [p for p in provides.get(key, []) if p["project_id"] != c["project_id"]]
            if matches:
                best = max(matches, key=lambda p: p["confidence"])
                confidence = (
                    CONF_CONTRACT
                    if best["contract_body"] and c["kind"] == "http"
                    else (CONF_METHOD_PATH if c["kind"] == "http" else CONF_NAME)
                )
                lk = Link(
                    names.get(c["project_id"], c["project_id"]),
                    names.get(best["project_id"], best["project_id"]),
                    c["kind"], c["normalized"],
                    _relation_for(c["kind"], c["direction"]),
                    confidence,
                    "contract" if best["contract_body"] else "method+path",
                )
                report.links.append(lk)
                continue

            # Mesma rota, verbo diferente: possível bug de integração.
            if c["kind"] == "http" and " " in c["normalized"]:
                verb, route = c["normalized"].split(" ", 1)
                outros = [
                    p for p in by_route.get(route, []) if p["project_id"] != c["project_id"]
                ]
                if outros:
                    p = outros[0]
                    report.divergences.append(
                        {
                            "from": names.get(c["project_id"], c["project_id"]),
                            "to": names.get(p["project_id"], p["project_id"]),
                            "consumed": c["normalized"],
                            "provided": p["normalized"],
                            "issue": f"método divergente ({verb} vs {p['normalized'].split(' ')[0]})",
                        }
                    )
                    conn.execute(
                        """INSERT OR REPLACE INTO unresolved
                           (id, src_project, kind, normalized, reason, detail, detected_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (hashlib.sha256(f"{c['project_id']}{c['normalized']}mm".encode()).hexdigest()[:32],
                         c["project_id"], c["kind"], c["normalized"], "method_mismatch",
                         p["normalized"], now),
                    )
                    continue

            if c["kind"] == "package":
                continue  # pacote externo sem provedor é o caso normal

            report.unresolved.append(
                {
                    "from": names.get(c["project_id"], c["project_id"]),
                    "kind": c["kind"],
                    "target": c["normalized"],
                }
            )
            conn.execute(
                """INSERT OR REPLACE INTO unresolved
                   (id, src_project, kind, normalized, reason, detail, detected_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (hashlib.sha256(f"{c['project_id']}{c['normalized']}np".encode()).hexdigest()[:32],
                 c["project_id"], c["kind"], c["normalized"], "no_provider", None, now),
            )

        minimum = cfg.federation.min_confidence
        for lk in report.links:
            if lk.confidence < minimum:
                report.suggestions.append(lk.__dict__)
                continue
            conn.execute(
                """INSERT OR REPLACE INTO cross_links
                   (id, src_project, dst_project, kind, normalized, relation,
                    confidence, evidence, resolved_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (lk.id, _pid(conn, lk.src_project), _pid(conn, lk.dst_project), lk.kind,
                 lk.normalized, lk.relation, lk.confidence, lk.evidence, now),
            )
        conn.commit()
    finally:
        conn.close()
    return report


def _relation_for(kind: str, direction: str) -> str:
    if kind == "event":
        return "subscribes" if direction == "consumes" else "publishes"
    return _RELATION.get(kind, "consumes")


def _pid(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else name


def workspace_dictionary(cfg: Config) -> dict[str, Any]:
    """O mapa do conjunto: em poucos KB, quem fala com quem."""
    conn = open_hub(cfg, read_only=True)
    try:
        projects = [
            {
                "name": r["name"], "kind": "http-service" if r["cloned"] else "external",
                "cloned": bool(r["cloned"]),
                "federation_only": not bool(r["cloned"]),
                "status": r["status"],
            }
            for r in conn.execute(
                "SELECT * FROM projects WHERE visibility != 'private' ORDER BY name"
            )
        ]
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM projects")}
        integrations = [
            {
                "from": names.get(r["src_project"], r["src_project"]),
                "to": names.get(r["dst_project"], r["dst_project"]),
                "via": r["normalized"],
                "relation": r["relation"],
                "confidence": round(r["confidence"], 2),
            }
            for r in conn.execute("SELECT * FROM cross_links ORDER BY normalized")
        ]
        unresolved = [
            {
                "from": names.get(r["src_project"], r["src_project"]),
                "target": r["normalized"],
                "reason": r["reason"],
                "detail": r["detail"],
            }
            for r in conn.execute("SELECT * FROM unresolved ORDER BY normalized")
        ]
    finally:
        conn.close()
    return {
        "schema_version": 1,
        "projects": projects,
        "integrations": integrations,
        "unresolved_consumes": [u for u in unresolved if u["reason"] == "no_provider"],
        "divergences": [u for u in unresolved if u["reason"] == "method_mismatch"],
    }


def find_contract(cfg: Config, kind: str, name: str) -> dict[str, Any] | None:
    conn = open_hub(cfg, read_only=True)
    try:
        row = conn.execute(
            """SELECT f.*, p.name AS project FROM federation_items f
               JOIN projects p ON p.id = f.project_id
               WHERE f.direction = 'provides' AND f.kind = ?
                 AND (f.normalized = ? COLLATE NOCASE OR f.raw = ? COLLATE NOCASE)
                 AND p.visibility != 'private'
               ORDER BY f.confidence DESC LIMIT 1""",
            (kind, name, name),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

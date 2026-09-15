"""Extração da superfície pública: o que o projeto PROVÊ e o que CONSOME.

Matéria-prima de toda a federação. Deriva do grafo referencial (Fase 3), que já
detecta rotas, eventos e dependências — aqui isso é promovido a artefato próprio.

Ver docs/17-multiprojeto-e-federacao.md.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ragx.core.ids import _digest
from ragx.graph.extractors.reference import _declared_deps, _normalize_route

# Publicação e assinatura de eventos, nos formatos mais comuns.
_EVENT_PUBLISH = (
    re.compile(r"""(?:publish|emit|dispatch|produce)\s*\(\s*['"]([\w.\-:]{3,})['"]""", re.I),
    re.compile(r"""new\s+(\w+Event)\s*\(""", re.I),
    re.compile(r"""class\s+(\w+Event)\b"""),
)
_EVENT_SUBSCRIBE = (
    re.compile(r"""(?:subscribe|on|listen|consume|handle)\s*\(\s*['"]([\w.\-:]{3,})['"]""", re.I),
    re.compile(r"""@(?:listener|subscriber|handler)\s*\(\s*['"]([\w.\-:]{3,})['"]""", re.I),
)
# Chamada HTTP saindo do projeto.
_HTTP_CALL = (
    re.compile(
        r"""(?:requests|httpx|axios|fetch|client|http)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*"""
        r"""[^'"]*['"]([^'"]*/[^'"]*)['"]""",
        re.I,
    ),
    re.compile(
        r"""fetch\s*\(\s*['"]([^'"]*/[^'"]*)['"]\s*,\s*\{[^}]*method\s*:\s*['"](\w+)['"]""",
        re.I | re.S,
    ),
)
_CONTRACT_FILES = ("openapi", "swagger", "asyncapi", ".proto", "schema.json")


@dataclass(frozen=True, slots=True)
class SurfaceItem:
    direction: str  # provides | consumes
    kind: str  # http | event | package | table
    normalized: str
    raw: str
    source_ref: str
    handler: str | None = None
    contract: str | None = None
    confidence: float = 1.0
    detected_by: str = "reference"
    manual: bool = False

    @property
    def id(self) -> str:
        return _digest(self.direction, self.kind, self.normalized)


def extract(conn: sqlite3.Connection, root: Path) -> list[SurfaceItem]:
    items: dict[str, SurfaceItem] = {}

    def add(item: SurfaceItem) -> None:
        prev = items.get(item.id)
        if prev is None or item.confidence > prev.confidence or item.manual:
            items[item.id] = item

    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT c.id, c.content, c.symbol, c.start_line, d.rel_path, d.lang, d.doc_kind
               FROM chunks c JOIN documents d ON d.id = c.document_id"""
        )
    ]

    # ── provides: endpoints já extraídos pelo grafo (confiança máxima) ──
    for r in conn.execute(
        """SELECT e.name, d.rel_path, c.symbol, c.start_line
           FROM entities e
           LEFT JOIN documents d ON d.id = e.document_id
           LEFT JOIN chunks c ON c.id = e.chunk_id
           WHERE e.type = 'endpoint'"""
    ):
        add(
            SurfaceItem(
                "provides", "http", r["name"], r["name"],
                source_ref=f"{r['rel_path']}:{r['start_line'] or 0}",
                handler=r["symbol"], detected_by="graph",
            )
        )

    # tabelas públicas
    for r in conn.execute(
        """SELECT e.name, d.rel_path FROM entities e
           LEFT JOIN documents d ON d.id = e.document_id WHERE e.type = 'table'"""
    ):
        add(
            SurfaceItem("provides", "table", r["name"], r["name"],
                        source_ref=r["rel_path"] or "?", detected_by="graph")
        )

    contracts = _contracts(rows)

    for r in rows:
        rel, content = r["rel_path"], r["content"]
        ref = f"{rel}:{r['start_line']}"

        # ── pacotes ──
        if Path(rel).name in ("composer.json", "package.json", "pyproject.toml",
                              "requirements.txt", "go.mod", "Gemfile"):
            for dep in _declared_deps(rel, content):
                if dep:
                    add(SurfaceItem("consumes", "package", dep.lower(), dep,
                                    source_ref=rel, detected_by="manifest"))
            published = _published_package(rel, content)
            if published:
                add(SurfaceItem("provides", "package", published.lower(), published,
                                source_ref=rel, detected_by="manifest"))

        if r["doc_kind"] != "code":
            continue

        # ── eventos ──
        for pattern in _EVENT_PUBLISH:
            for name in pattern.findall(content):
                add(SurfaceItem("provides", "event", _norm_event(name), name,
                                source_ref=ref, handler=r["symbol"], confidence=0.85))
        for pattern in _EVENT_SUBSCRIBE:
            for name in pattern.findall(content):
                add(SurfaceItem("consumes", "event", _norm_event(name), name,
                                source_ref=ref, handler=r["symbol"], confidence=0.85))

        # ── chamadas HTTP saindo ──
        for method, path in _http_calls(content):
            if not path.startswith(("/", "http")):
                continue
            route = _strip_host(path)
            if route.count("/") < 1:
                continue
            normalized = f"{method.upper()} {_normalize_route(route)}"
            confidence = 0.95 if "{" not in route and "$" not in route else 0.6
            add(
                SurfaceItem("consumes", "http", normalized, f"{method.upper()} {path}",
                            source_ref=ref, handler=r["symbol"],
                            contract=contracts.get(normalized), confidence=confidence,
                            detected_by="http-client-literal")
            )

    _attach_manual(root, items, add)
    return sorted(items.values(), key=lambda i: (i.direction, i.kind, i.normalized))


def _http_calls(content: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _HTTP_CALL[0].findall(content):
        out.append((m[0], m[1]))
    for m in _HTTP_CALL[1].findall(content):
        out.append((m[1], m[0]))
    return out


def _strip_host(path: str) -> str:
    if path.startswith("http"):
        parts = path.split("/", 3)
        return "/" + parts[3] if len(parts) > 3 else "/"
    return path


def _norm_event(name: str) -> str:
    return re.sub(r"[_\s]+", ".", name.strip()).lower()


def _published_package(rel: str, content: str) -> str | None:
    try:
        name = Path(rel).name
        if name == "package.json":
            data = json.loads(content)
            return data.get("name") if not data.get("private") else None
        if name == "composer.json":
            return json.loads(content).get("name")
        if name == "pyproject.toml":
            import tomllib

            return tomllib.loads(content).get("project", {}).get("name")
    except Exception:
        return None
    return None


def _contracts(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Contrato declarado é a evidência de maior confiança que existe."""
    out: dict[str, str] = {}
    for r in rows:
        low = r["rel_path"].lower()
        if not any(marker in low for marker in _CONTRACT_FILES):
            continue
        out.setdefault("__files__", "")
        for m in re.finditer(r"""['"](/[\w/{}\-.]*)['"]\s*:""", r["content"]):
            route = _normalize_route(m.group(1))
            for verb in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                out[f"{verb} {route}"] = r["rel_path"]
    out.pop("__files__", None)
    return out


def _attach_manual(root: Path, items: dict[str, SurfaceItem], add: Any) -> None:
    """Declaração curada à mão VENCE o derivado — heurística erra, humano decide."""
    path = root / "knowledge" / "federation" / "manual.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for direction in ("provides", "consumes"):
        for entry in data.get(direction, []) or []:
            kind = entry.get("kind", "http")
            raw = entry.get("value") or entry.get("normalized") or ""
            if not raw:
                continue
            normalized = (
                f"{entry['method'].upper()} {_normalize_route(entry['path'])}"
                if kind == "http" and entry.get("path")
                else raw
            )
            add(
                SurfaceItem(direction, kind, normalized, raw,
                            source_ref=entry.get("source", "manual.json"),
                            handler=entry.get("handler"), contract=entry.get("contract"),
                            confidence=1.0, detected_by="manual", manual=True)
            )


def persist(conn: sqlite3.Connection, items: list[SurfaceItem]) -> int:
    conn.execute("DELETE FROM federation_surface")
    conn.executemany(
        """INSERT OR REPLACE INTO federation_surface
           (id, direction, kind, normalized, raw, handler, contract, source_ref,
            confidence, detected_by, manual)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (i.id, i.direction, i.kind, i.normalized, i.raw, i.handler, i.contract,
             i.source_ref, i.confidence, i.detected_by, int(i.manual))
            for i in items
        ],
    )
    return len(items)

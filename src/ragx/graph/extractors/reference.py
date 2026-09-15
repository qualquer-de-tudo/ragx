"""Camada 2 — referencial. Determinística, heurística, sem LLM.

Regra dura: só cria aresta para entidade que JÁ EXISTE. Sem isso, o extrator
começa a inventar nós e o grafo vira ficção.

Ver docs/06-grafo.md.
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pathspec import GitIgnoreSpec

from ragx.graph.store import Entity, EntityType, Relation, RelationType

CATALOG_PATH = Path(__file__).parent / "technologies.yaml"

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|::|->|\.)")
# Espaco/tab mas NAO newline: com \s puro, "import os" engolia o arquivo
# inteiro numa unica captura (a regex atravessava as quebras de linha).
# O `[^\n]*` final é o detalhe que importa: com `[\w.,\s]+` a classe incluía
# newline e um `import os` capturava o arquivo inteiro numa única correspondência.
_IMPORT_PY = re.compile(
    r"^\s*(?:from\s+([\w.]+)|import\s+([\w.,][^\n]*))",
    re.MULTILINE,
)
_IMPORT_JS = re.compile(r"""(?:from\s+|require\()\s*['"]([^'"]+)['"]""")
_IMPORT_PHP = re.compile(r"^\s*use\s+([\w\\]+)", re.MULTILINE)
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([\w.]+)", re.IGNORECASE
)
_ROUTES = (
    # Laravel / Symfony
    re.compile(r"""Route::(get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]""", re.I),
    # Express / Fastify
    re.compile(r"""\b(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]""", re.I),
    # FastAPI / Flask
    re.compile(r"""@\w+\.(get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]""", re.I),
    re.compile(r"""@\w+\.route\s*\(\s*['"]([^'"]+)['"].*?methods\s*=\s*\[['"](\w+)""", re.I | re.S),
)


@dataclass
class ReferenceResult:
    entities: list[Entity]
    relations: list[Relation]
    unresolved: int = 0


def load_catalog() -> dict[str, Any]:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


def extract(
    conn: sqlite3.Connection, known: dict[str, str], root: Path | None = None
) -> ReferenceResult:
    """`known` mapeia chunk_id -> entity_id (saída da camada 1)."""
    catalog = load_catalog()
    entities: list[Entity] = []
    relations: list[Relation] = []
    unresolved = 0

    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT c.id, c.document_id, c.kind, c.symbol, c.heading_path, c.content,
                      d.rel_path, d.lang, d.doc_kind
               FROM chunks c JOIN documents d ON d.id = c.document_id"""
        )
    ]

    # Índice nome -> entidades existentes. Só ligamos para o que já existe.
    name_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(
        "SELECT id, type, name, qualified_name, document_id FROM entities "
        "WHERE type IN ('class','function','method','file')"
    ):
        name_index[r["name"].lower()].append(dict(r))

    owner_of_chunk = dict(known)
    file_entity_of_doc = {
        r["document_id"]: r["id"]
        for r in conn.execute(
            "SELECT id, document_id FROM entities WHERE type = 'file' AND document_id IS NOT NULL"
        )
    }

    tech_entities, tech_relations = _technologies(rows, catalog, file_entity_of_doc, root)
    entities.extend(tech_entities)
    relations.extend(tech_relations)

    for r in rows:
        src = owner_of_chunk.get(r["id"]) or file_entity_of_doc.get(r["document_id"])
        if src is None:
            continue

        # Referências a entidades conhecidas.
        # Prosa que cita `AuthService.login()` MENCIONA; só código CHAMA.
        is_code = r["doc_kind"] == "code"
        rel_type = RelationType.CALLS if is_code else RelationType.MENTIONS
        confidence = 0.75 if is_code else 0.6
        for match in _CALL.finditer(r["content"]):
            target = match.group(1).lower()
            if len(target) < 3:
                continue
            for cand in name_index.get(target, []):
                if cand["id"] == src or cand["document_id"] == r["document_id"]:
                    continue  # referência no mesmo arquivo já é `contains`
                relations.append(
                    Relation(
                        src, cand["id"], rel_type,
                        confidence=confidence, source="reference",
                        evidence_chunk_id=r["id"],
                    )
                )

        # imports
        for module in _imports(r["content"], r["lang"]):
            hit = _resolve_module(module, name_index)
            if hit:
                relations.append(
                    Relation(src, hit, RelationType.IMPORTS, source="reference",
                             evidence_chunk_id=r["id"])
                )
            else:
                unresolved += 1

        # documentação -> entidade de código
        if r["doc_kind"] == "doc":
            for token in set(_IDENT.findall(r["heading_path"] or "")) | set(
                _IDENT.findall(r["content"][:2000])
            ):
                for cand in name_index.get(token.lower(), []):
                    if cand["type"] in ("class", "function", "method"):
                        relations.append(
                            Relation(
                                cand["id"], src, RelationType.DOCUMENTED_BY,
                                confidence=0.8, source="reference", evidence_chunk_id=r["id"],
                            )
                        )

        # tabelas e endpoints
        for table in set(_CREATE_TABLE.findall(r["content"])):
            ent = Entity(
                EntityType.TABLE, table, table, document_id=r["document_id"],
                chunk_id=r["id"], source="reference",
            )
            entities.append(ent)
            relations.append(
                Relation(src, ent.id, RelationType.CONTAINS, source="reference",
                         evidence_chunk_id=r["id"])
            )

        for method, path in _endpoints(r["content"]):
            normalized = f"{method.upper()} {_normalize_route(path)}"
            ent = Entity(
                EntityType.ENDPOINT, normalized, normalized,
                document_id=r["document_id"], chunk_id=r["id"], source="reference",
            )
            entities.append(ent)
            relations.append(
                Relation(src, ent.id, RelationType.CONTAINS, source="reference",
                         evidence_chunk_id=r["id"])
            )

    return ReferenceResult(_dedupe(entities), _dedupe_rel(relations), unresolved)


# ── tecnologias ─────────────────────────────────────────────────────────
def _technologies(
    rows: list[dict[str, Any]],
    catalog: dict[str, Any],
    file_entity_of_doc: dict[str, str],
    root: Path | None,
) -> tuple[list[Entity], list[Relation]]:
    techs = catalog["technologies"]
    by_package: dict[str, str] = {}
    by_import: dict[str, str] = {}
    file_specs: list[tuple[GitIgnoreSpec, str]] = []
    for t in techs:
        for p in t.get("packages", []):
            by_package[p.lower()] = t["name"]
        for i in t.get("imports", []):
            by_import[i.lower()] = t["name"]
        if t.get("files"):
            file_specs.append((GitIgnoreSpec.from_lines(t["files"]), t["name"]))

    found: dict[str, tuple[float, str]] = {}  # nome -> (confiança, evidência)
    evidence_chunk: dict[str, str] = {}

    for r in rows:
        rel = r["rel_path"]
        # sinal mais forte: dependência declarada em manifesto
        if PurePosixPath(rel).name in (
            "composer.json", "package.json", "pyproject.toml", "requirements.txt",
            "go.mod", "Gemfile",
        ):
            for dep in _declared_deps(rel, r["content"]):
                name = by_package.get(dep.lower())
                if name:
                    found[name] = (1.0, rel)
                    evidence_chunk.setdefault(name, r["id"])
        # sinal médio: import no código
        for module in _imports(r["content"], r["lang"]):
            name = by_import.get(module.split(".")[0].lower())
            if name and found.get(name, (0.0, ""))[0] < 0.9:
                found[name] = (0.9, rel)
                evidence_chunk.setdefault(name, r["id"])
        # sinal por presença de arquivo característico
        for spec, name in file_specs:
            if spec.match_file(rel) and found.get(name, (0.0, ""))[0] < 0.95:
                found[name] = (0.95, rel)
                evidence_chunk.setdefault(name, r["id"])

    entities: list[Entity] = []
    relations: list[Relation] = []
    for name, (conf, evidence) in found.items():
        ent = Entity(
            EntityType.TECHNOLOGY, name, name, summary=f"evidência: {evidence}",
            confidence=conf, source="reference",
        )
        entities.append(ent)
        doc_id = next(
            (r["document_id"] for r in rows if r["rel_path"] == evidence), None
        )
        src = file_entity_of_doc.get(doc_id) if doc_id else None
        if src:
            relations.append(
                Relation(src, ent.id, RelationType.USES, confidence=conf, source="reference",
                         evidence_chunk_id=evidence_chunk.get(name))
            )
    return entities, relations


def _declared_deps(rel_path: str, content: str) -> list[str]:
    import json

    name = PurePosixPath(rel_path).name
    try:
        if name in ("composer.json", "package.json"):
            data = json.loads(content)
            out: list[str] = []
            for section in (
                "require", "require-dev", "dependencies", "devDependencies",
                "peerDependencies",
            ):
                out.extend(data.get(section, {}) or {})
            return out
        if name == "pyproject.toml":
            data = tomllib.loads(content)
            deps = list(data.get("project", {}).get("dependencies", []) or [])
            for extra in (data.get("project", {}).get("optional-dependencies", {}) or {}).values():
                deps.extend(extra)
            return [re.split(r"[<>=!\[~ ]", d)[0] for d in deps]
        if name in ("requirements.txt", "Gemfile", "go.mod"):
            return [
                re.split(r"[<>=!\[~ ]", line.strip())[0]
                for line in content.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
    except Exception:
        return []
    return []


# ── utilidades ──────────────────────────────────────────────────────────
def _imports(content: str, lang: str | None) -> list[str]:
    out: list[str] = []
    if lang == "python":
        for a, b in _IMPORT_PY.findall(content):
            if a:
                out.append(a)
            if b:
                out.extend(x.strip() for x in b.split(",") if x.strip())
    elif lang in ("javascript", "typescript"):
        out.extend(_IMPORT_JS.findall(content))
    elif lang == "php":
        out.extend(_IMPORT_PHP.findall(content))
    return [m for m in out if m]


def _resolve_module(module: str, name_index: dict[str, list[dict[str, Any]]]) -> str | None:
    tail = module.replace("\\", ".").split(".")[-1].lower()
    for cand in name_index.get(tail, []):
        if cand["type"] in ("file", "class"):
            return str(cand["id"])
    return None


def _endpoints(content: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pattern in _ROUTES[:3]:
        out.extend((m[0], m[1]) for m in pattern.findall(content))
    for m in _ROUTES[3].findall(content):
        out.append((m[1], m[0]))
    return out


def _normalize_route(path: str) -> str:
    """Rotas equivalentes entre stacks precisam virar a MESMA forma — é o que
    permite cruzar consumes/provides na Fase 11."""
    p = re.sub(r"\{[^}]*\}", "{}", path)
    p = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "{}", p)
    p = re.sub(r"<[^>]*>", "{}", p)
    p = re.sub(r"%[sd]", "{}", p)
    p = re.sub(r"/+", "/", p)
    return p if p.startswith("/") else "/" + p


def _dedupe(entities: list[Entity]) -> list[Entity]:
    seen: dict[str, Entity] = {}
    for e in entities:
        prev = seen.get(e.id)
        if prev is None or e.confidence > prev.confidence:
            seen[e.id] = e
    return list(seen.values())


def _dedupe_rel(relations: list[Relation]) -> list[Relation]:
    seen: dict[str, Relation] = {}
    for r in relations:
        prev = seen.get(r.id)
        if prev is None or r.confidence > prev.confidence:
            seen[r.id] = r
    return list(seen.values())

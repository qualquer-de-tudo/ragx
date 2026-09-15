"""Knowledge Dictionary — o mapa barato do projeto.

Um agente que chega no repositório não sabe o que perguntar. Sem orientação ele
faz a pergunta mais cara possível ("me explique todo o projeto"). O dicionário
cabe em poucos KB e responde "o que existe aqui" antes de gastar contexto.

Regra dura: TUDO que é determinístico é gerado sem LLM, e todo item carrega
`evidence` — sem isso ninguém pode auditar, e alucinação entra por aí.

Ver docs/08-dictionary.md.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from ragx.config import Config
from ragx.core.ids import SCHEMA_VERSION
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db, utcnow

SCHEMA = 1
_CONVENTION_MIN = 3
_MAX_ITEMS = 60
# O dicionário é lido ANTES de gastar contexto: se ele próprio for caro,
# perde a razão de existir. Ver docs/08-dictionary.md.
_GLOSSARY_MAX = 20
_DOCS_MAX = 40
_TOKEN_TARGET = 8000


@dataclass
class DictionaryReport:
    path: str = ""
    sections: dict[str, int] = field(default_factory=dict)
    bytes_written: int = 0
    redacted_items: int = 0
    semantic: bool = False


def build(cfg: Config, semantic: bool = False) -> tuple[dict[str, Any], DictionaryReport]:
    report = DictionaryReport(semantic=semantic)
    with open_db(cfg.db_path, read_only=True) as conn:
        docs = [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY rel_path")]
        entities = [dict(r) for r in conn.execute("SELECT * FROM entities")]
        relations = [dict(r) for r in conn.execute("SELECT * FROM relations")]
        stats = {
            "documents": len(docs),
            "chunks": int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]),
            "entities": len(entities),
            "relations": len(relations),
            "embeddings": int(conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]),
        }
        doc_path = {d["id"]: d["rel_path"] for d in docs}
        data = {
            "schema_version": SCHEMA,
            "project": {
                "name": cfg.project.name,
                "id": cfg.project.id,
                "kind": cfg.project.kind,
                "generated_at": utcnow(),
                "ragx_schema": SCHEMA_VERSION,
            },
            "technologies": _technologies(entities, relations, doc_path),
            "services": _services(conn, entities, relations, doc_path),
            "modules": _modules(conn, docs),
            "entrypoints": _entrypoints(entities, doc_path),
            "data_stores": _data_stores(entities, doc_path),
            "conventions": _conventions(docs, entities),
            "docs": _docs(docs),
            "concepts": _concepts(entities, relations, doc_path),
            "glossary": _glossary(docs, entities),
            "stats": stats,
        }

    data, report.redacted_items = _scrub(cfg, data)
    data = _fit_budget(data)
    report.sections = {
        k: len(v) for k, v in data.items() if isinstance(v, list | dict) and k != "project"
    }
    return data, report


# ── seções determinísticas ──────────────────────────────────────────────
def _technologies(
    entities: list[dict], relations: list[dict], doc_path: dict[str, str]
) -> list[dict[str, Any]]:
    out = []
    for e in entities:
        if e["type"] != "technology":
            continue
        evidence = [
            doc_path[r["src_id"]]
            for r in relations
            if r["dst_id"] == e["id"] and r["src_id"] in doc_path
        ]
        if not evidence and e["summary"]:
            evidence = [e["summary"].replace("evidência: ", "")]
        out.append(
            {
                "name": e["name"],
                "evidence": sorted(set(evidence))[:5],
                "confidence": round(float(e["confidence"]), 2),
            }
        )
    return sorted(out, key=lambda t: (-t["confidence"], t["name"]))[:_MAX_ITEMS]


def _services(
    conn: sqlite3.Connection, entities: list[dict], relations: list[dict],
    doc_path: dict[str, str],
) -> list[dict[str, Any]]:
    """Classe cujo nome segue a convenção de serviço, ou que é referenciada de fora."""
    by_id = {e["id"]: e for e in entities}
    incoming: Counter[str] = Counter()
    for r in relations:
        if r["type"] in ("calls", "imports", "depends_on"):
            incoming[r["dst_id"]] += 1

    out = []
    for e in entities:
        if e["type"] != "class":
            continue
        looks_like_service = any(
            e["name"].endswith(s)
            for s in ("Service", "Repository", "Client", "Manager", "Handler", "Gateway",
                      "Provider", "Engine", "Scanner", "Builder", "Store")
        )
        if not looks_like_service and incoming[e["id"]] < 3:
            continue
        deps = sorted(
            {
                by_id[r["dst_id"]]["name"]
                for r in relations
                if r["src_id"] == e["id"]
                and r["type"] in ("uses", "calls", "imports")
                and r["dst_id"] in by_id
                and by_id[r["dst_id"]]["type"] in ("technology", "class")
            }
        )
        documented = sorted(
            {
                by_id[r["dst_id"]]["qualified_name"]
                for r in relations
                if r["src_id"] == e["id"] and r["type"] == "documented_by"
                and r["dst_id"] in by_id
            }
        )
        out.append(
            {
                "name": e["name"],
                "path": doc_path.get(e["document_id"], ""),
                "summary": e["summary"],
                "depends_on": deps[:8],
                "documented_by": documented[:4],
                "referenced_by": incoming[e["id"]],
            }
        )
    return sorted(out, key=lambda s: (-s["referenced_by"], s["name"]))[:_MAX_ITEMS]


def _modules(conn: sqlite3.Connection, docs: list[dict]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "chunks": 0})
    chunk_by_doc = {
        r["document_id"]: r["n"]
        for r in conn.execute("SELECT document_id, COUNT(*) n FROM chunks GROUP BY document_id")
    }
    for d in docs:
        parts = PurePosixPath(d["rel_path"]).parts
        module = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if len(parts) > 1 else ".")
        counts[module]["files"] += 1
        counts[module]["chunks"] += chunk_by_doc.get(d["id"], 0)
    return [
        {"name": m, "files": v["files"], "chunks": v["chunks"]}
        for m, v in sorted(counts.items(), key=lambda kv: -kv[1]["chunks"])
    ][:_MAX_ITEMS]


def _entrypoints(entities: list[dict], doc_path: dict[str, str]) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "kind": "http",
                "value": e["name"],
                "source": doc_path.get(e["document_id"], ""),
            }
            for e in entities
            if e["type"] == "endpoint"
        ),
        key=lambda x: x["value"],
    )[:_MAX_ITEMS]


def _data_stores(entities: list[dict], doc_path: dict[str, str]) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "name": e["name"],
                "kind": "table",
                "defined_in": doc_path.get(e["document_id"], ""),
            }
            for e in entities
            if e["type"] == "table"
        ),
        key=lambda x: x["name"],
    )[:_MAX_ITEMS]


def _conventions(docs: list[dict], entities: list[dict]) -> list[dict[str, Any]]:
    """Padrão repetido >= 3 vezes vira convenção declarada, com evidência."""
    out: list[dict[str, Any]] = []
    suffix_dirs: dict[tuple[str, str], list[str]] = defaultdict(list)
    doc_path = {d["id"]: d["rel_path"] for d in docs}

    for e in entities:
        if e["type"] != "class":
            continue
        path = doc_path.get(e["document_id"], "")
        if not path:
            continue
        for suffix in ("Service", "Repository", "Controller", "Parser", "Scanner",
                       "Engine", "Store", "Client", "Handler"):
            if e["name"].endswith(suffix):
                folder = str(PurePosixPath(path).parent)
                suffix_dirs[(suffix, folder)].append(path)

    for (suffix, folder), paths in suffix_dirs.items():
        if len(paths) >= _CONVENTION_MIN:
            out.append(
                {
                    "rule": f"Classes com sufixo {suffix} ficam em {folder}/",
                    "occurrences": len(paths),
                    "confidence": round(min(0.6 + 0.1 * len(paths), 0.95), 2),
                    "evidence": sorted(paths)[:4],
                }
            )

    ext_counter = Counter(PurePosixPath(d["rel_path"]).suffix for d in docs if d["rel_path"])
    test_files = [d["rel_path"] for d in docs if "test" in d["rel_path"].lower()]
    if len(test_files) >= _CONVENTION_MIN:
        folders = Counter(str(PurePosixPath(p).parent).split("/")[0] for p in test_files)
        folder, n = folders.most_common(1)[0]
        out.append(
            {
                "rule": f"Testes ficam em {folder}/",
                "occurrences": n,
                "confidence": 0.9,
                "evidence": sorted(test_files)[:4],
            }
        )
    if ext_counter:
        main_ext, n = ext_counter.most_common(1)[0]
        if main_ext and n >= _CONVENTION_MIN:
            out.append(
                {
                    "rule": f"Extensão predominante: {main_ext}",
                    "occurrences": n,
                    "confidence": 1.0,
                    "evidence": [d["rel_path"] for d in docs
                                 if d["rel_path"].endswith(main_ext)][:3],
                }
            )
    return sorted(out, key=lambda c: -c["occurrences"])[:_MAX_ITEMS]


def _docs(docs: list[dict]) -> list[dict[str, Any]]:
    return [
        {"path": d["rel_path"], "title": d["title"]}
        for d in docs
        if d["doc_kind"] == "doc" and d["title"]
    ][:_DOCS_MAX]


def _concepts(
    entities: list[dict], relations: list[dict], doc_path: dict[str, str]
) -> dict[str, list[str]]:
    """Agrupa entidades por raiz de nome — determinístico, sem LLM.

    É mais pobre que clustering semântico, e honesto: o que sai daqui tem
    evidência direta no nome dos símbolos.
    """
    groups: dict[str, set[str]] = defaultdict(set)
    tokens = Counter()
    for e in entities:
        if e["type"] not in ("class", "technology", "endpoint", "table"):
            continue
        for tok in _split_words(e["name"]):
            if len(tok) > 3:
                tokens[tok.lower()] += 1
    for tok, n in tokens.most_common(24):
        if n < 2:
            continue
        for e in entities:
            if e["type"] in ("class", "technology", "table") and tok in e["name"].lower():
                groups[tok].add(e["name"])
    return {
        k: sorted(v)[:12] for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:20]
        if len(v) >= 2
    }


def _glossary(docs: list[dict], entities: list[dict]) -> list[dict[str, Any]]:
    """Siglas dos títulos de documentação — determinístico e auditável."""
    out: dict[str, dict[str, Any]] = {}
    for d in docs:
        title = d["title"] or ""
        for word in title.replace("-", " ").split():
            clean = word.strip("()[]:,.")
            if 2 <= len(clean) <= 6 and clean.isupper() and clean.isalpha():
                item = out.setdefault(clean, {"term": clean, "evidence": [], "seen": 0})
                item["seen"] += 1
                if d["rel_path"] not in item["evidence"] and len(item["evidence"]) < 2:
                    item["evidence"].append(d["rel_path"])
    # Sigla que aparece uma vez só é ruído, não glossário.
    return sorted(
        (g for g in out.values() if g["seen"] >= 2),
        key=lambda g: (-g["seen"], g["term"]),
    )[:_GLOSSARY_MAX]


def _split_words(name: str) -> list[str]:
    import re

    return [w for w in re.split(r"(?<=[a-z0-9])(?=[A-Z])|[_\-. ]", name) if w]


# ── segurança: o dicionário é artefato COMPARTILHADO ────────────────────
def _scrub(cfg: Config, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Re-scan antes de gravar. O dicionário vai para o Git e para o `.rag`,
    então é superfície de vazamento de primeira classe."""
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    removed = 0

    def clean(node: Any) -> Any:
        nonlocal removed
        if isinstance(node, str):
            findings = gate.scanner.scan_content("dictionary.json", node)
            if findings:
                removed += 1
                return "«RAGX:REDACTED»"
            return node
        if isinstance(node, list):
            return [clean(v) for v in node]
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items()}
        return node

    return clean(data), removed


# ── escrita estável ─────────────────────────────────────────────────────
def write(cfg: Config, data: dict[str, Any], out_dir: str | None = None) -> DictionaryReport:
    target = cfg.root / (out_dir or "knowledge")
    target.mkdir(parents=True, exist_ok=True)
    path = target / "dictionary.json"
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(body, encoding="utf-8", newline="\n")
    return DictionaryReport(path=str(path), bytes_written=len(body.encode("utf-8")))


def stable_digest(data: dict[str, Any]) -> str:
    """Hash ignorando `generated_at` — regeneração sem mudanças precisa bater."""
    import hashlib

    copy = json.loads(json.dumps(data))
    copy.get("project", {}).pop("generated_at", None)
    payload = json.dumps(copy, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load(cfg: Config, out_dir: str | None = None) -> dict[str, Any] | None:
    path = cfg.root / (out_dir or "knowledge") / "dictionary.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _fit_budget(data: dict[str, Any], target: int = _TOKEN_TARGET) -> dict[str, Any]:
    """Agrega em vez de listar tudo quando o dicionário passa do alvo.

    Um mapa que custa mais que a pergunta que ele evita não serve para nada.
    """
    from ragx.tokens import count_tokens

    def size() -> int:
        return count_tokens(json.dumps(data, ensure_ascii=False))

    # Corta primeiro as seções mais verbosas e menos densas em informação.
    for section, floor in (("glossary", 8), ("docs", 15), ("services", 15),
                           ("data_stores", 10), ("modules", 10)):
        while size() > target and isinstance(data.get(section), list) and len(data[section]) > floor:
            data[section] = data[section][: max(len(data[section]) * 2 // 3, floor)]
            data.setdefault("truncated", {})[section] = "listagem agregada por orçamento"
    return data

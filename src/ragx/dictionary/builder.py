"""Knowledge Dictionary — o mapa barato do projeto.

Um agente que chega no repositório não sabe o que perguntar. Sem orientação ele
faz a pergunta mais cara possível ("me explique todo o projeto"). O dicionário
cabe em poucos KB e responde "o que existe aqui" antes de gastar contexto.

Regra dura: TUDO que é determinístico é gerado sem LLM, e todo item carrega
`evidence` — sem isso ninguém pode auditar, e alucinação entra por aí.

Ver docs/08-dictionary.md.
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from ragx.config import Config
from ragx.core.ids import SCHEMA_VERSION
from ragx.security.scanner import SecurityScanner, load_ruleset
from ragx.storage.db import open_db, utcnow

SCHEMA = 1
_CONVENTION_MIN = 3
_MAX_ITEMS = 60
# O dicionário é lido ANTES de gastar contexto: se ele próprio for caro,
# perde a razão de existir. Ver docs/08-dictionary.md.
_GLOSSARY_MAX = 20
_DOCS_MAX = 40
_TOKEN_TARGET = 4000
#: tamanho máximo de um resumo extrativo (primeira linha de docstring / primeiro parágrafo)
_SUMMARY_MAX = 160
#: um módulo com mais que esta fração dos chunks é subdividido em mais um nível de pasta
_MODULE_SPLIT_SHARE = 0.25
#: um símbolo documentado por mais documentos que isto é genérico demais para ser um conceito
_CONCEPT_MAX_DOCS = 4


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


# ── resumos extrativos (RAGX-0109): do que o código e a documentação JÁ dizem, sem LLM ─────────
def _primeira_linha(texto: str | None) -> str | None:
    """Primeira linha não vazia de um texto, sem ponto final e limitada; `None` se não houver (nunca inventa)."""
    if not texto:
        return None
    for linha in texto.strip().splitlines():
        linha = linha.strip().strip("*#/ \t")
        if linha:
            linha = linha.rstrip(".:;")
            return linha[: _SUMMARY_MAX - 1] + "…" if len(linha) > _SUMMARY_MAX else linha
    return None


def _fatos_da_classe(content: str) -> dict[str, Any] | None:
    """Docstring, bases e métodos de uma classe a partir do texto do chunk; `None` se não for Python legível."""
    try:
        tree = ast.parse(textwrap.dedent(content))
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases]
            metodos = [
                n for n in node.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and not (n.name.startswith("__") and n.name.endswith("__"))
            ]
            decoradores = [ast.unparse(d) for d in node.decorator_list]
            return {
                "doc": _primeira_linha(ast.get_docstring(node)),
                "bases": bases,
                "metodos": len(metodos),
                "decoradores": decoradores,
            }
    return None


_DOC_COMENTARIO = re.compile(r"/\*\*(.+?)\*/", re.S)


def _resumo_de_classe(content: str, fatos: dict[str, Any] | None) -> str | None:
    if fatos is not None:
        return fatos["doc"]
    m = _DOC_COMENTARIO.search(content[:1500])  # TS/JS/PHP: o bloco de documentação logo antes da classe
    return _primeira_linha(m.group(1)) if m else None


_DOC_MODULO = re.compile(r'''^\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\')''', re.S)


def _resumo_do_documento(conn: sqlite3.Connection, document_id: str | None) -> str | None:
    """Primeira linha do docstring do MÓDULO (primeiro chunk do arquivo), quando a classe não tem o dela."""
    if not document_id:
        return None
    row = conn.execute(
        "SELECT content FROM chunks WHERE document_id = ? ORDER BY ordinal LIMIT 1", (document_id,)
    ).fetchone()
    if not row:
        return None
    m = _DOC_MODULO.match(row["content"][:1200])
    return _primeira_linha(m.group(1)) if m else None


def _eh_so_dados(nome: str, fatos: dict[str, Any] | None, metodos: int) -> bool:
    """Exceção, enum, DTO e esquema não são serviço (RAGX-0110). `metodos`: quantos métodos o grafo registra na classe."""
    if nome.endswith(("Error", "Exception")):
        return True
    if fatos is None:
        return False
    if metodos == 0 and not fatos["bases"]:
        return True  # sem nenhum método e sem herança: só campos (DTO), mesmo sem `@dataclass`
    bases = " ".join(fatos["bases"])
    if re.search(r"Exception|Error|Enum|BaseModel|TypedDict|NamedTuple|Protocol", bases):
        return True
    return any("dataclass" in d for d in fatos["decoradores"])


def _resumo_do_modulo(conn: sqlite3.Connection, modulo: str) -> str | None:
    """README da pasta (primeiro parágrafo), docstring do `__init__.py` ou README de uma pasta-mãe que NÃO seja a raiz
    (`src/app/electron` herda o de `src/app`: é o mesmo aplicativo); `None` se nada disso disser algo."""
    achou = _resumo_da_pasta(conn, modulo)
    if achou or modulo == ".":
        return achou
    partes = PurePosixPath(modulo).parts
    for n in range(len(partes) - 1, 0, -1):  # nunca a raiz do projeto: o README dela fala do projeto, não da pasta
        achou = _readme_da_pasta(conn, "/".join(partes[:n]))
        if achou:
            return achou
    return None


def _resumo_da_pasta(conn: sqlite3.Connection, modulo: str) -> str | None:
    return _readme_da_pasta(conn, modulo) or _init_da_pasta(conn, modulo)


def _readme_da_pasta(conn: sqlite3.Connection, modulo: str) -> str | None:
    base = "" if modulo == "." else modulo.rstrip("/") + "/"
    for nome in ("README.md", "readme.md"):
        row = conn.execute(
            "SELECT c.content FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.rel_path = ? ORDER BY c.ordinal LIMIT 3",
            (base + nome,),
        ).fetchall()
        for r in row:
            for linha in r["content"].splitlines():
                t = linha.strip()
                if t and not t.startswith(("#", "|", "```", "-", ">", "[", "!", "<")) and len(t) > 12:
                    return _primeira_linha(t)
    return None


def _init_da_pasta(conn: sqlite3.Connection, modulo: str) -> str | None:
    base = "" if modulo == "." else modulo.rstrip("/") + "/"
    row = conn.execute(
        "SELECT c.content FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.rel_path = ? ORDER BY c.ordinal LIMIT 1",
        (base + "__init__.py",),
    ).fetchone()
    if row:
        try:
            return _primeira_linha(ast.get_docstring(ast.parse(row["content"])))
        except (SyntaxError, ValueError):
            return None
    return None


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

    metodos_de: Counter[str] = Counter()
    for r in relations:
        if r["type"] == "contains" and by_id.get(r["dst_id"], {}).get("type") == "method":
            metodos_de[r["src_id"]] += 1

    out = []
    for e in entities:
        if e["type"] != "class" or e["name"].startswith("_"):
            continue  # símbolo privado não entra no mapa
        looks_like_service = any(
            e["name"].endswith(s)
            for s in ("Service", "Repository", "Client", "Manager", "Handler", "Gateway",
                      "Provider", "Engine", "Scanner", "Builder", "Store")
        )
        if not looks_like_service and incoming[e["id"]] < 3:
            continue
        content = ""
        if e["chunk_id"]:
            row = conn.execute("SELECT content FROM chunks WHERE id = ?", (e["chunk_id"],)).fetchone()
            content = row["content"] if row else ""
        fatos = _fatos_da_classe(content) if content else None
        if _eh_so_dados(e["name"], fatos, metodos_de[e["id"]]):
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
                # a documentação de verdade, não o changelog, as tarefas e os planos que citam qualquer nome
                and not by_id[r["dst_id"]]["qualified_name"].startswith(
                    ("CHANGELOG", "task/", "docs/superpowers/", "agents/", "SECURITY")
                )
            }
        )
        out.append(
            {
                "name": e["name"],
                "path": doc_path.get(e["document_id"], ""),
                "summary": e["summary"]
                or _resumo_de_classe(content, fatos)
                or _resumo_do_documento(conn, e["document_id"]),
                "depends_on": [d for d in deps if not d.startswith("_")][:5],
                "documented_by": documented[:2],
                "referenced_by": incoming[e["id"]],
            }
        )
    return sorted(out, key=lambda s: (-s["referenced_by"], s["name"]))[:_MAX_ITEMS]


def _modules(conn: sqlite3.Connection, docs: list[dict]) -> list[dict[str, Any]]:
    """Pastas de dois níveis; a que concentra muito do código é aberta em mais um (`src/ragx` vira `src/ragx/indexing`)."""
    chunk_by_doc = {
        r["document_id"]: r["n"]
        for r in conn.execute("SELECT document_id, COUNT(*) n FROM chunks GROUP BY document_id")
    }

    def nome(parts: tuple[str, ...], niveis: int) -> str:
        if len(parts) > niveis:
            return "/".join(parts[:niveis])
        return parts[0] if len(parts) > 1 else "."

    por_doc = [(PurePosixPath(d["rel_path"]).parts, chunk_by_doc.get(d["id"], 0)) for d in docs]
    total = sum(n for _, n in por_doc) or 1
    dois: dict[str, int] = defaultdict(int)
    for parts, n in por_doc:
        dois[nome(parts, 2)] += n
    grandes = {m for m, n in dois.items() if n / total > _MODULE_SPLIT_SHARE}

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "chunks": 0})
    for parts, n in por_doc:
        m = nome(parts, 2)
        if m in grandes and len(parts) > 3:
            m = nome(parts, 3)
        counts[m]["files"] += 1
        counts[m]["chunks"] += n
    ordenados = sorted(counts.items(), key=lambda kv: -kv[1]["chunks"])[:_MAX_ITEMS]
    return [
        {"name": m, "files": v["files"], "chunks": v["chunks"], "summary": _resumo_do_modulo(conn, m)}
        for m, v in ordenados
    ]


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
            and not doc_path.get(e["document_id"], "").startswith(("tests/", "test/", "fixtures/"))
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
    """Conceito = o que um documento da documentação descreve: o título dele e as classes que ele documenta.

    Vem da relação `documented_by` do grafo (RAGX-0110), não de agrupar nomes por pedaço de string, e as classes saem
    ordenadas pelo grau no grafo. Símbolo privado não entra.
    """
    by_id = {e["id"]: e for e in entities}
    grau: Counter[str] = Counter()
    for r in relations:
        grau[r["src_id"]] += 1
        grau[r["dst_id"]] += 1
    # Só a documentação do projeto (`docs/`, fora de planos e specs) conta como conceito; changelog, tarefas e planos
    # citam qualquer nome. E um símbolo citado por muitos documentos (`Config`, `Task`) é genérico: não descreve nenhum.
    def conta(path: str) -> bool:
        return path.startswith("docs/") and not path.startswith(("docs/superpowers/", "docs/adr/"))

    quantos: Counter[str] = Counter()
    pares: list[tuple[str, str]] = []
    for r in relations:
        if r["type"] != "documented_by":
            continue
        src, dst = by_id.get(r["src_id"]), by_id.get(r["dst_id"])
        if not src or not dst or src["type"] != "class" or src["name"].startswith("_"):
            continue
        if not conta(doc_path.get(dst.get("document_id") or "", "")):
            continue
        pares.append((src["id"], dst.get("summary") or dst["name"]))
        quantos[src["id"]] += 1
    por_doc: dict[str, set[str]] = defaultdict(set)
    for sid, titulo in pares:
        if quantos[sid] <= _CONCEPT_MAX_DOCS:
            por_doc[titulo].add(sid)
    ordenados = sorted(por_doc.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out: dict[str, list[str]] = {}
    for titulo, ids in ordenados:
        if len(ids) < 2:
            continue
        nomes = [by_id[i]["name"] for i in sorted(ids, key=lambda i: (-grau[i], by_id[i]["name"]))]
        out[titulo] = nomes[:6]
        if len(out) >= 12:
            break
    return out


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


# ── níveis de leitura (RAGX-0111) ───────────────────────────────────────
#: `get_dictionary(level=N)`: o agente começa barato e aprofunda. Os níveis são RECORTES DE LEITURA do mesmo
#: `dictionary.json` (o formato em disco não muda), e cada um é superconjunto do anterior: mesmas seções, mais itens e
#: mais campos por item. Custo medido neste repositório: nível 0 ≈ 400 tokens, nível 1 ≈ 1.700, nível 2 (completo) ≈ 3.700.
LEVELS = (0, 1, 2)

#: por nível: seção -> (máximo de itens, campos mantidos por item; `None` = o item inteiro)
_NIVEIS: dict[int, dict[str, tuple[int, tuple[str, ...] | None]]] = {
    0: {
        "technologies": (8, ("name",)),
        "services": (8, ("name",)),
        "modules": (6, ("name", "summary")),
        "entrypoints": (5, ("kind", "value")),
    },
    1: {
        "technologies": (_MAX_ITEMS, ("name", "confidence")),
        "services": (12, ("name", "path", "summary")),
        "modules": (_MAX_ITEMS, ("name", "summary", "files")),
        "entrypoints": (_MAX_ITEMS, None),
        "conventions": (_MAX_ITEMS, ("rule", "occurrences")),
        "docs": (10, None),
    },
}


def at_level(data: dict[str, Any], level: int) -> dict[str, Any]:
    """O recorte do dicionário no `level` (0, 1 ou 2). `2` devolve tudo, como sempre foi."""
    if level not in LEVELS:
        raise ValueError(f"nível desconhecido: {level} (use 0, 1 ou 2)")
    if level == 2:
        return data
    plano = _NIVEIS[level]
    out: dict[str, Any] = {"schema_version": data.get("schema_version"), "level": level}
    projeto = data.get("project") or {}
    out["project"] = {k: projeto[k] for k in ("name", "id", "kind") if k in projeto}
    out["stats"] = data.get("stats", {})
    for secao, (maximo, campos) in plano.items():
        itens = data.get(secao)
        if not isinstance(itens, list):
            continue
        recorte = itens[:maximo]
        if campos is not None:
            recorte = [{k: i[k] for k in campos if k in i} for i in recorte]
        out[secao] = recorte
    return out


# ── segurança: o dicionário é artefato COMPARTILHADO ────────────────────
def _scrub(cfg: Config, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Re-scan antes de gravar. O dicionário vai para o Git e para o `.rag`,
    então é superfície de vazamento de primeira classe."""
    # Só o scanner (RAGX-0150): o `SecurityGate` construía um `IgnoreEngine` e caminhava a árvore (28-41 ms) para usar
    # apenas `gate.scanner`. Mesmos valores que o gate usa por padrão (`ruleset` padrão, `min_entropy=3.0`).
    scanner = SecurityScanner(load_ruleset(), min_entropy=3.0)
    removed = 0

    def clean(node: Any) -> Any:
        nonlocal removed
        if isinstance(node, str):
            findings = scanner.scan_content("dictionary.json", node)
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
    # `generated_at` (em `project`) muda sozinho a cada geração: só regrava se o CONTEÚDO mudou (RAGX-0148)
    from ragx.sync.stable_write import write_text_if_changed

    write_text_if_changed(path, body, volatile=("generated_at",))
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

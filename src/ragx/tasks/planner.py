"""Documentation Planner — quais documentos, fundamentados no que já existe.

O planner **não escreve texto**. Ele decide quais documentos o trabalho exige,
ordena por dependência entre tipos, e produz esqueletos que já carregam o que o
índice sabe sobre o assunto. O texto é escrito pelo agente, na tarefa
correspondente.

A regra que não se quebra: **documentação nunca nasce isolada do conhecimento
existente**. Um documento que o planner não conseguiu fundamentar sai com a
lacuna marcada — inventar é pior que admitir o buraco, porque o buraco vira
tarefa e a invenção vira verdade.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from ragx.config import Config
from ragx.tasks.models import Analysis

DOCTYPES_PATH = Path(__file__).parent / "doctypes.yaml"


@dataclass(frozen=True, slots=True)
class DocType:
    id: str
    label: str
    folder: str
    requires: tuple[str, ...]
    triggers: tuple[str, ...]
    min_score: int
    sections: tuple[str, ...]


@dataclass
class PlannedDoc:
    doc_type: str = ""
    title: str = ""
    rel_path: str = ""
    sections: list[str] = field(default_factory=list)
    grounding: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    body: str = ""


@dataclass
class DocPlan:
    docs: list[PlannedDoc] = field(default_factory=list)
    context_sources: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    prior_decisions: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_doctypes() -> dict[str, DocType]:
    data = yaml.safe_load(DOCTYPES_PATH.read_text(encoding="utf-8"))
    return {
        t["id"]: DocType(
            id=t["id"], label=t["label"], folder=t["folder"],
            requires=tuple(t.get("requires", [])),
            triggers=tuple(t.get("triggers", [])),
            min_score=int(t.get("min_score", 50)),
            sections=tuple(t.get("sections", [])),
        )
        for t in data["types"]
    }


def plan(cfg: Config, analysis: Analysis, project_id: str) -> DocPlan:
    """Decide os documentos e os fundamenta. Não escreve em disco."""
    tipos = load_doctypes()
    scores = analysis.scores.as_dict()

    escolhidos = {
        t.id for t in tipos.values()
        if any(scores.get(g, 0) >= t.min_score for g in t.triggers)
    }
    # Fechar o conjunto sobre `requires`: propor um desenho técnico sem a
    # decisão arquitetural que o governa produz um documento que ninguém
    # consegue revisar.
    mudou = True
    while mudou:
        mudou = False
        for tid in list(escolhidos):
            for req in tipos[tid].requires:
                if req not in escolhidos:
                    escolhidos.add(req)
                    mudou = True

    contexto = _gather(cfg, analysis)
    p = DocPlan(
        context_sources=contexto["sources"],
        entities=contexto["entities"],
        technologies=contexto["technologies"],
        prior_decisions=contexto["decisions"],
    )

    slug = _slug(analysis.request)
    for tid in _topological(escolhidos, tipos):
        t = tipos[tid]
        doc = PlannedDoc(
            doc_type=t.id,
            title=f"{t.label} — {_title(analysis.request)}",
            rel_path=f"knowledge/{t.folder}/{slug}.md",
            sections=list(t.sections),
        )
        doc.grounding, doc.gaps = _ground(t, contexto, analysis)
        doc.body = _skeleton(doc, t, analysis, project_id)
        p.docs.append(doc)
    return p


def _topological(ids: set[str], tipos: dict[str, DocType]) -> list[str]:
    """Ordem estável: `requires` primeiro, depois alfabética para desempatar.

    Sem o desempate, a mesma análise produziria ordens diferentes entre
    execuções e o diff do `knowledge/` nunca ficaria vazio.
    """
    ordem: list[str] = []
    visto: set[str] = set()

    def visita(tid: str, pilha: tuple[str, ...] = ()) -> None:
        if tid in visto or tid in pilha:
            return
        for req in sorted(tipos[tid].requires):
            if req in ids:
                visita(req, (*pilha, tid))
        visto.add(tid)
        ordem.append(tid)

    for tid in sorted(ids):
        visita(tid)
    return ordem


def _gather(cfg: Config, analysis: Analysis) -> dict[str, list[str]]:
    """O que o projeto já sabe sobre o assunto.

    Cada falha é tolerada individualmente: um projeto sem grafo ainda produz
    plano com as fontes da busca, e um sem índice nenhum produz plano só com
    lacunas — que é a resposta certa, não um erro.
    """
    out: dict[str, list[str]] = {
        "sources": [], "entities": [], "technologies": [], "decisions": [],
    }
    if not cfg.db_path.exists():
        return out

    try:
        from ragx.search.service import search

        r = search(cfg, analysis.request, mode="hybrid", limit=10)
        vistos: list[str] = []
        for hit in r.results:
            p = hit.document_path
            if p not in vistos:
                vistos.append(p)
        out["sources"] = vistos[:8]
    except Exception:
        pass

    try:
        from ragx.graph.store import GraphStore
        from ragx.storage.db import open_db

        with open_db(cfg.db_path, read_only=True) as conn:
            store = GraphStore(conn)
            for termo in _terms(analysis.request)[:5]:
                for e in store.find(termo)[:3]:
                    nome = e["name"] if isinstance(e, dict) else getattr(e, "name", "")
                    if nome and nome not in out["entities"]:
                        out["entities"].append(nome)
    except Exception:
        pass

    try:
        from ragx.dictionary import builder

        d = builder.load(cfg) or {}
        out["technologies"] = [
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in (d.get("technologies") or [])
        ][:10]
    except Exception:
        pass

    # Decisões vêm do ÍNDICE, não de um `glob` em `docs/adr/`. Varrer o
    # projeto aqui faria deste módulo um terceiro leitor de filesystem, e o
    # teste arquitetural existe justamente para impedir que isso cresça sem
    # ninguém decidir — o índice já sabe quais ADRs existem.
    try:
        from ragx.storage.db import open_db

        termos = set(_terms(analysis.request))
        with open_db(cfg.db_path, read_only=True) as conn:
            linhas = conn.execute(
                "SELECT rel_path FROM documents WHERE rel_path LIKE '%adr%' "
                "OR rel_path LIKE '%decision%' ORDER BY rel_path"
            )
            for r in linhas:
                caminho = r["rel_path"]
                if termos & set(_terms(caminho)):
                    out["decisions"].append(caminho)
    except Exception:
        pass
    return out


def _ground(
    t: DocType, contexto: dict[str, list[str]], analysis: Analysis,
) -> tuple[list[str], list[str]]:
    """Referências que sustentam o documento, e as lacunas que sobraram."""
    grounding = list(contexto["sources"][:5])
    if t.id in ("architecture", "decision"):
        grounding += contexto["decisions"][:3]
    if t.id in ("technical", "database", "api"):
        grounding += [f"entidade: {e}" for e in contexto["entities"][:4]]

    gaps: list[str] = []
    if not grounding:
        gaps.append(
            f"nenhum documento ou código existente cobre "
            f"'{_title(analysis.request)}'; este {t.label.lower()} precisa de "
            f"entrevista com o time antes de ser escrito"
        )
    if t.id == "performance" and analysis.scores.as_dict()["complexity"] < 60:
        gaps.append("sem medição anterior registrada; medir antes de propor mudança")
    if t.id == "security" and not contexto["decisions"]:
        gaps.append("nenhuma decisão de segurança registrada para este território")
    return grounding, gaps


def _skeleton(
    doc: PlannedDoc, t: DocType, analysis: Analysis, project_id: str,
) -> str:
    """Esqueleto com o contexto DENTRO. Sem texto inventado."""
    linhas = [
        f"# {doc.title}",
        "",
        f"> Planejado pelo RAGX a partir de: *{_title(analysis.request)}*",
        f"> Projeto `{project_id}` · classificação `{analysis.classification}` · "
        f"complexidade `{analysis.complexity}`",
        "",
    ]
    if doc.grounding:
        linhas += ["## Conhecimento existente considerado", ""]
        linhas += [f"- `{g}`" for g in doc.grounding]
        linhas.append("")
    for gap in doc.gaps:
        linhas += [f"> **Pendente:** {gap}", ""]

    for secao in t.sections:
        linhas += [f"## {secao}", "", "> **Pendente:** escrever.", ""]

    linhas += [
        "---",
        "",
        "*Esqueleto gerado pelo Documentation Planner. O conteúdo é escrito pelo",
        "agente na tarefa correspondente — o RAGX não inventa texto.*",
        "",
    ]
    return "\n".join(linhas)


_STOP = {
    "de", "da", "do", "para", "com", "em", "um", "uma", "o", "a", "os", "as",
    "e", "no", "na", "que", "por", "the", "of", "to", "for", "and", "novo",
    "nova", "usar",
}


def _terms(texto: str) -> list[str]:
    palavras = re.findall(r"[\wÀ-ÿ]{3,}", (texto or "").lower())
    return [p for p in palavras if p not in _STOP]


def _title(request: str) -> str:
    limpo = " ".join((request or "").split())
    return limpo[:80] + ("…" if len(limpo) > 80 else "")


def _slug(request: str) -> str:
    termos = _terms(request)[:6]
    base = "-".join(termos) or "trabalho"
    return re.sub(r"[^a-z0-9-]+", "", base.lower())[:60] or "trabalho"

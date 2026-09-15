"""Serviço de alto nível: analisar, planejar, aplicar.

É o que a CLI e o MCP chamam. Mantém os dois falando exatamente a mesma língua
— divergência entre o que o humano e o agente conseguem fazer vira bug
relatado por agente, que é o mais caro de diagnosticar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ragx.config import Config
from ragx.tasks import planner
from ragx.tasks.analyzer import analyze
from ragx.tasks.decomposer import decompose, project_id_for
from ragx.tasks.models import Analysis, Classification
from ragx.tasks.store import TaskRepository, open_tasks_db


@dataclass
class Plan:
    analysis: Analysis = field(default_factory=Analysis)
    project_id: str = ""
    documents: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    dependencies: int = 0
    skipped_tracks: list[str] = field(default_factory=list)
    applied: bool = False
    written_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "analysis": self.analysis.to_dict(),
            "documents": self.documents,
            "tasks": self.tasks,
            "dependencies": self.dependencies,
            "skipped_tracks": self.skipped_tracks,
            "applied": self.applied,
            "written_files": self.written_files,
        }


def analyze_request(cfg: Config, request: str) -> Analysis:
    return analyze(cfg, request)


def plan_work(
    cfg: Config, request: str, apply: bool = False,
    write_docs: bool = True, analysis: Analysis | None = None,
) -> Plan:
    """Analisa e, se o pedido merecer, monta o projeto.

    Pedido trivial **não** vira projeto: devolver um board de doze tarefas para
    "corrigir um typo" é a burocracia que faz as pessoas desligarem a
    ferramenta.
    """
    a = analysis or analyze(cfg, request)
    p = Plan(analysis=a, project_id=project_id_for(request))

    if a.classification is Classification.DIRECT_EXECUTION:
        return p

    docplan = planner.plan(cfg, a, p.project_id)
    p.documents = [
        {
            "doc_type": d.doc_type, "title": d.title, "rel_path": d.rel_path,
            "sections": d.sections, "grounding": d.grounding, "gaps": d.gaps,
        }
        for d in (docplan.docs if a.requires_documentation else [])
    ]
    if not a.requires_documentation:
        docplan.docs = []

    d = decompose(cfg, a, docplan, p.project_id, repo=None)
    p.tasks = [_task_dict(t) for t in d.tasks]
    p.dependencies = len(d.edges)
    p.skipped_tracks = d.skipped_tracks

    if not apply:
        return p

    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        if repo.get_project(p.project_id) is not None:
            raise ValueError(
                f"projeto {p.project_id} já existe — use `ragx task list "
                f"--project {p.project_id}` para ver o board atual"
            )
        repo.create_project(
            p.project_id, _name(request), request, a.to_dict(),
            max_concurrency=cfg.tasks.max_concurrency,
        )
        decompose(cfg, a, docplan, p.project_id, repo=repo)
        for doc in docplan.docs:
            repo.add_document(
                f"{p.project_id}-{doc.doc_type}", p.project_id, doc.doc_type,
                doc.title, doc.rel_path, doc.grounding, doc.gaps,
            )
        conn.commit() if conn.in_transaction else None

    if write_docs and docplan.docs:
        p.written_files = _write_skeletons(cfg, docplan)

    p.applied = True
    return p


def _write_skeletons(cfg: Config, docplan: object) -> list[str]:
    """Grava os esqueletos em `knowledge/<tipo>/`.

    Vive aqui e não no planner de propósito: o planner decide e fundamenta, sem
    tocar em disco, e continua testável sem filesystem.
    """
    escritos: list[str] = []
    for doc in docplan.docs:  # type: ignore[attr-defined]
        destino = cfg.root / doc.rel_path
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            # Documento já escrito por alguém não é sobrescrito por esqueleto.
            continue
        destino.write_text(doc.body, encoding="utf-8", newline="\n")
        escritos.append(doc.rel_path)
    return escritos


def _task_dict(t: object) -> dict[str, Any]:
    return {
        "id": t.id, "seq": t.seq, "title": t.title, "type": t.type,  # type: ignore[attr-defined]
        "track": t.track, "priority": t.priority,  # type: ignore[attr-defined]
        "status": str(t.status),  # type: ignore[attr-defined]
        "acceptance_criteria": list(t.acceptance_criteria),  # type: ignore[attr-defined]
        "files_scope": list(t.files_scope),  # type: ignore[attr-defined]
        "test_requirements": list(t.test_requirements),  # type: ignore[attr-defined]
        "requires_approval": t.requires_approval,  # type: ignore[attr-defined]
    }


def _name(request: str) -> str:
    limpo = " ".join((request or "").split())
    return limpo[:60] + ("…" if len(limpo) > 60 else "")


def status_panel(cfg: Config) -> dict[str, Any]:
    """O painel da §31 do pedido — tarefas, conhecimento e agendamento."""
    from ragx.tasks.worker import list_schedules

    out: dict[str, Any] = {"tasks": {}, "projects": [], "knowledge": {},
                           "scheduler": {}}
    try:
        with open_tasks_db(cfg, read_only=True) as conn:
            repo = TaskRepository(conn)
            out["tasks"] = repo.counts()
            out["projects"] = [
                {"id": p["id"], "name": p["name"], "status": p["status"]}
                for p in repo.list_projects()
            ]
            agendas = list_schedules(repo)
            out["scheduler"] = {
                "total": len(agendas),
                "enabled": sum(1 for s in agendas if s["enabled"]),
                "next": min(
                    (s["next_run_at"] for s in agendas
                     if s["enabled"] and s["next_run_at"]),
                    default=None,
                ),
            }
    except Exception as exc:
        out["tasks_error"] = str(exc)

    try:
        from ragx.storage.db import open_db

        with open_db(cfg.db_path, read_only=True) as conn:
            out["knowledge"] = {
                "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                "relations": conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
            }
    except Exception:
        out["knowledge"] = {}
    return out

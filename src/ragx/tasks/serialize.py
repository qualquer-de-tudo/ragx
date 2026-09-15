"""Tarefas no Git: a DEFINIÇÃO viaja, a EXECUÇÃO fica (ADR-0014).

    knowledge/tasks/projects/*.json     projeto, análise, estratégia
    knowledge/tasks/tasks/*.json        tarefa, dependências, critérios
    knowledge/tasks/decisions/*.json    decisões registradas

Fora daqui, e de propósito: runs, tentativas, logs, locks, retry. Versionar
isso produziria conflito de merge em todo pull request, sobre um arquivo que
ninguém revisa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.tasks.models import PRIORITY_RANK, Status, merge_status
from ragx.tasks.store import TaskRepository, open_tasks_db, utcnow

FOLDER = "tasks"

#: Campos que descrevem O TRABALHO. Tudo que descreve a EXECUÇÃO fica fora.
_TASK_FIELDS = (
    "id", "project_id", "parent_task_id", "seq", "title", "description", "type",
    "track", "status", "priority", "complexity", "acceptance_criteria",
    "required_context", "required_skills", "files_scope",
    "security_requirements", "performance_requirements", "test_requirements",
    "agent", "requires_approval", "max_retries",
)


@dataclass
class TaskSyncReport:
    projects: int = 0
    tasks: int = 0
    decisions: int = 0
    edges: int = 0
    files_written: int = 0
    removed: int = 0
    conflicts: list[str] = field(default_factory=list)
    #: Execução não volta do Git. É dito, não escondido.
    history_lost: bool = False
    warnings: list[str] = field(default_factory=list)


def _dump(path: Path, data: Any) -> int:
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    atual = path.read_text(encoding="utf-8") if path.is_file() else None
    if atual == body:
        return 0  # diff vazio quando nada mudou
    path.write_text(body, encoding="utf-8", newline="\n")
    return 1


def _prune(folder: Path, keep: set[str]) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for p in folder.iterdir():
        if p.is_file() and p.name not in keep:
            p.unlink()
            n += 1
    return n


def serialize(cfg: Config, out_dir: str = "knowledge") -> TaskSyncReport:
    """Grava a definição do trabalho. Determinístico: mesmo estado, mesmos bytes."""
    r = TaskSyncReport()
    alvo = cfg.root / out_dir / FOLDER
    if not (cfg.state_dir / "ragx.sqlite").exists():
        return r

    with open_tasks_db(cfg, read_only=True) as conn:
        repo = TaskRepository(conn)
        projetos = repo.list_projects()
        if not projetos:
            r.removed += _prune(alvo / "projects", set())
            r.removed += _prune(alvo / "tasks", set())
            r.removed += _prune(alvo / "decisions", set())
            return r

        keep_p: set[str] = set()
        for p in projetos:
            nome = f"{p['id']}.json"
            keep_p.add(nome)
            r.files_written += _dump(alvo / "projects" / nome, {
                "id": p["id"], "name": p["name"], "request": p["request"],
                "classification": p["classification"], "complexity": p["complexity"],
                "strategy": p["strategy"], "status": p["status"],
                "analysis": json.loads(p["analysis_json"] or "{}"),
                "max_concurrency": p["max_concurrency"],
            })
            r.projects += 1
        r.removed += _prune(alvo / "projects", keep_p)

        keep_t: set[str] = set()
        for t in repo.list_tasks(limit=100_000):
            nome = f"{t['id']}.json"
            keep_t.add(nome)
            corpo = {k: t.get(k) for k in _TASK_FIELDS}
            corpo["requires_approval"] = bool(corpo.get("requires_approval"))
            corpo["dependencies"] = [
                {"id": d["id"], "kind": d["kind"]}
                for d in repo.dependencies_of(t["id"])
            ]
            r.edges += len(corpo["dependencies"])
            r.files_written += _dump(alvo / "tasks" / nome, corpo)
            r.tasks += 1
        r.removed += _prune(alvo / "tasks", keep_t)

        keep_d: set[str] = set()
        for d in repo.decisions():
            nome = f"{d['id']}.json"
            keep_d.add(nome)
            r.files_written += _dump(alvo / "decisions" / nome, {
                k: d.get(k) for k in
                ("id", "project_id", "task_id", "title", "context", "problem",
                 "options", "decision", "consequences", "status", "rel_path")
            })
            r.decisions += 1
        r.removed += _prune(alvo / "decisions", keep_d)

    _dump(alvo / "manifest.json", {
        "schema_version": 1,
        "counts": {"projects": r.projects, "tasks": r.tasks,
                   "decisions": r.decisions, "dependencies": r.edges},
        "note": (
            "Definição do trabalho. Execução (runs, tentativas, logs, locks, "
            "retry) NÃO é versionada — ver ADR-0014."
        ),
        "generated_at": utcnow(),
    })
    return r


def rehydrate(cfg: Config, out_dir: str = "knowledge") -> TaskSyncReport:
    """Reconstrói o board a partir do Git.

    O que volta: projetos, tarefas, dependências, critérios, decisões, status.
    O que NÃO volta: histórico de execução local. Isso é reportado, não
    escondido — um `sync` que devolve um board íntegro e um histórico vazio
    sem avisar leva alguém a procurar um log que não existe mais.
    """
    r = TaskSyncReport()
    alvo = cfg.root / out_dir / FOLDER
    if not (alvo / "manifest.json").is_file():
        return r

    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        historico = int(
            conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0]
        )

        for arquivo in sorted((alvo / "projects").glob("*.json")):
            p = _read(arquivo, r)
            if p is None:
                continue
            if repo.get_project(p["id"]) is None:
                repo.create_project(
                    p["id"], p["name"], p["request"], p.get("analysis", {}),
                    max_concurrency=int(p.get("max_concurrency", 1)),
                )
            repo.set_project_status(p["id"], p.get("status", "active"))
            r.projects += 1

        arestas: list[tuple[str, str, str]] = []
        for arquivo in sorted((alvo / "tasks").glob("*.json")):
            t = _read(arquivo, r)
            if t is None:
                continue
            for d in t.get("dependencies", []):
                arestas.append((t["id"], d["id"], d.get("kind", "depends_on")))
            _upsert_task(repo, t, r)
            r.tasks += 1

        for task_id, depende, kind in arestas:
            try:
                from ragx.tasks.models import DependencyKind

                repo.add_dependency(task_id, depende, DependencyKind(kind))
                r.edges += 1
            except Exception as exc:
                r.warnings.append(f"dependência {task_id}->{depende}: {exc}")

        for arquivo in sorted((alvo / "decisions").glob("*.json")):
            d = _read(arquivo, r)
            if d is None:
                continue
            repo.add_decision(
                d["id"], d["title"], project_id=d.get("project_id"),
                task_id=d.get("task_id"), context=d.get("context", ""),
                problem=d.get("problem", ""), options=d.get("options", []),
                decision=d.get("decision", ""),
                consequences=d.get("consequences", ""),
                status=d.get("status", "proposed"), rel_path=d.get("rel_path"),
            )
            r.decisions += 1

        repo.promote_ready()
        conn.commit() if conn.in_transaction else None

    r.history_lost = historico == 0 and r.tasks > 0
    return r


def _read(path: Path, r: TaskSyncReport) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        r.warnings.append(f"{path.name}: {exc}")
        return None


def _upsert_task(repo: TaskRepository, t: dict[str, Any], r: TaskSyncReport) -> None:
    from ragx.tasks.models import Task

    existente = repo.get(t["id"])
    remoto = Status(t.get("status", "pending"))
    # `running` que veio do Git é execução de OUTRA máquina: aqui não existe
    # processo segurando essa tarefa, e deixá-la assim a prenderia para sempre.
    if remoto in (Status.RUNNING, Status.QUEUED):
        remoto = Status.PENDING

    if existente is None:
        repo.create_task(Task(
            id=t["id"], project_id=t["project_id"],
            parent_task_id=t.get("parent_task_id"), seq=int(t.get("seq", 0)),
            title=t["title"], description=t.get("description", ""),
            type=t.get("type", "technical"), track=t.get("track", "backend"),
            status=Status.PENDING, priority=t.get("priority", "medium"),
            complexity=t.get("complexity", "medium"),
            acceptance_criteria=t.get("acceptance_criteria") or ["(sem critério registrado)"],
            required_context=t.get("required_context", []),
            required_skills=t.get("required_skills", []),
            files_scope=t.get("files_scope", []),
            security_requirements=t.get("security_requirements", []),
            performance_requirements=t.get("performance_requirements", []),
            test_requirements=t.get("test_requirements", []),
            agent=t.get("agent"), requires_approval=bool(t.get("requires_approval")),
            max_retries=int(t.get("max_retries", 3)),
        ))
        alvo = remoto
    else:
        local = Status(existente["status"])
        alvo = merge_status(local, remoto)
        if local != remoto:
            r.conflicts.append(
                f"{t['id']}: local={local} git={remoto} -> {alvo}"
            )
        _update_definition(repo, t)

    atual = Status((repo.get(t["id"]) or {}).get("status", "pending"))
    if atual != alvo:
        # `restore_status`, não `set_status`: reidratar não é transição.
        # `pending -> completed` é inválido durante a execução, e é exatamente
        # o que um `git pull` traz quando o colega concluiu a tarefa.
        repo.restore_status(t["id"], alvo)


def _update_definition(repo: TaskRepository, t: dict[str, Any]) -> None:
    """Atualiza o que é definição. Não toca em nada de execução."""
    repo.conn.execute(
        """UPDATE tasks SET title = ?, description = ?, type = ?, track = ?,
               priority = ?, priority_rank = ?, complexity = ?,
               acceptance_criteria = ?, files_scope = ?, test_requirements = ?,
               security_requirements = ?, performance_requirements = ?,
               requires_approval = ?, max_retries = ?, updated_at = ?
             WHERE id = ?""",
        (
            t["title"], t.get("description", ""), t.get("type", "technical"),
            t.get("track", "backend"), t.get("priority", "medium"),
            PRIORITY_RANK.get(t.get("priority", "medium"), 1),
            t.get("complexity", "medium"),
            json.dumps(t.get("acceptance_criteria", []), ensure_ascii=False),
            json.dumps(t.get("files_scope", []), ensure_ascii=False),
            json.dumps(t.get("test_requirements", []), ensure_ascii=False),
            json.dumps(t.get("security_requirements", []), ensure_ascii=False),
            json.dumps(t.get("performance_requirements", []), ensure_ascii=False),
            int(bool(t.get("requires_approval"))), int(t.get("max_retries", 3)),
            utcnow(), t["id"],
        ),
    )

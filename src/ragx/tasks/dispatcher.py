"""Dispatcher, contexto por tarefa, validação e processamento de resultado.

O RAGX é a fila e o árbitro; o agente é o executor (ADR-0015). Este módulo é a
fronteira entre os dois: entrega trabalho pronto, recebe resultado, verifica o
que dá para verificar, e libera o que ficou pronto.

O validador é **determinístico e sem juízo sobre qualidade de código**. Ele
confere escopo, evidência e gate. Um validador que fingisse avaliar qualidade
aprovaria o errado com autoridade, que é pior que não validar.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ragx.config import Config
from ragx.tasks.models import (
    EventType,
    Status,
    TaskResult,
    Validation,
)
from ragx.tasks.store import TaskRepository


@dataclass
class Delivery:
    """O que o agente recebe ao reivindicar."""

    task: dict[str, Any] = field(default_factory=dict)
    run_id: int = 0
    context: str = ""
    context_tokens: int = 0
    sources: list[str] = field(default_factory=list)
    dependencies_done: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task, "run_id": self.run_id, "context": self.context,
            "context_tokens": self.context_tokens, "sources": self.sources,
            "dependencies_done": self.dependencies_done,
            "decisions": self.decisions,
        }


# ── contexto ────────────────────────────────────────────────────────────
def build_task_context(
    cfg: Config, repo: TaskRepository, task: dict[str, Any],
    budget: int | None = None,
) -> tuple[str, int, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Monta o contexto da TAREFA — não do projeto.

    O agente não precisa do repositório inteiro, e dar isso a ele é a forma
    mais cara de piorar a resposta. Aqui entra: o que a busca acha sobre o
    título e a descrição, o resultado das dependências já concluídas, e as
    decisões registradas que tocam o assunto.
    """
    orcamento = budget or cfg.context.default_tokens
    consulta = f"{task['title']}. {task.get('description', '')}".strip()

    partes: list[str] = [
        f"# Tarefa {task['id']} — {task['title']}",
        "",
        task.get("description", ""),
        "",
        "## Critérios de aceite",
        "",
    ]
    partes += [f"- {c}" for c in task.get("acceptance_criteria", [])]

    if task.get("files_scope"):
        partes += ["", "## Escopo de arquivos", "",
                   "Mexer fora daqui faz a validação recusar o resultado.", ""]
        partes += [f"- `{p}`" for p in task["files_scope"]]

    for rotulo, chave in (
        ("Requisitos de segurança", "security_requirements"),
        ("Requisitos de performance", "performance_requirements"),
        ("Requisitos de teste", "test_requirements"),
    ):
        if task.get(chave):
            partes += ["", f"## {rotulo}", ""]
            partes += [f"- {x}" for x in task[chave]]

    # Resultado das dependências: é o que faz uma tarefa alimentar a próxima
    # sem ninguém lembrar de contar.
    concluidas: list[dict[str, Any]] = []
    for dep in repo.dependencies_of(task["id"]):
        if dep["status"] != str(Status.COMPLETED):
            continue
        r = repo.latest_result(dep["id"])
        if r is None:
            continue
        payload = r.get("payload") or {}
        concluidas.append({
            "task_id": dep["id"], "title": dep["title"],
            "summary": payload.get("summary", ""),
            "decisions": payload.get("decisions", []),
            "remaining_risks": payload.get("remaining_risks", []),
        })
    if concluidas:
        partes += ["", "## O que as tarefas anteriores descobriram", ""]
        for c in concluidas:
            partes.append(f"**{c['task_id']} — {c['title']}**")
            if c["summary"]:
                partes.append(f"  {c['summary']}")
            for risco in c["remaining_risks"][:3]:
                partes.append(f"  - risco em aberto: {risco}")
            partes.append("")

    decisoes = [
        {"id": d["id"], "title": d["title"], "decision": d["decision"]}
        for d in repo.decisions(task.get("project_id"))
        if d["status"] in ("proposed", "accepted")
    ][:8]
    if decisoes:
        partes += ["## Decisões já registradas neste projeto", ""]
        partes += [f"- **{d['title']}**: {d['decision'] or 'em aberto'}" for d in decisoes]
        partes.append("")

    # O conhecimento do índice entra por último e com o orçamento que sobrou —
    # o que é da tarefa nunca é cortado para caber conhecimento de apoio.
    sources: list[str] = []
    cabecalho = "\n".join(partes)
    restante = max(400, orcamento - _tokens(cabecalho))
    try:
        from ragx.context.engine import build_context

        pack = build_context(cfg, consulta, budget=restante)
        if pack.fragments:
            partes += ["## Conhecimento relacionado", ""]
            for f in pack.fragments:
                partes.append(
                    f"### `{f.document_path}`:{f.start_line}-{f.end_line}"
                )
                partes += ["", f.content, ""]
            sources = list(pack.sources)
    except Exception:
        partes += ["", "> **Nota:** índice indisponível; contexto limitado à tarefa.", ""]

    corpo = "\n".join(partes)
    return corpo, _tokens(corpo), sources, concluidas, decisoes


def _tokens(texto: str) -> int:
    try:
        from ragx.tokens import count_tokens

        return count_tokens(texto)
    except Exception:
        return max(1, len(texto) // 4)


# ── dispatcher ──────────────────────────────────────────────────────────
class TaskDispatcher:
    def __init__(self, cfg: Config, repo: TaskRepository, worker: str = "agent"):
        self.cfg = cfg
        self.repo = repo
        self.worker = worker

    def next(self, project_id: str | None = None) -> dict[str, Any] | None:
        """A próxima executável — sem reivindicar. Leitura pura."""
        prontas = self.repo.ready_tasks(project_id=project_id, limit=1)
        return prontas[0] if prontas else None

    def claim(
        self, task_id: str | None = None, project_id: str | None = None,
        budget: int | None = None,
    ) -> Delivery | None:
        """Reivindica com lease e devolve tarefa + contexto pronto.

        Sem `task_id`, pega a próxima da fila. A corrida é resolvida no
        repositório: se outro ganhou, tenta a seguinte em vez de falhar — duas
        sessões pedindo trabalho ao mesmo tempo é o caso normal, não o erro.
        """
        candidatas = (
            [task_id] if task_id
            else [t["id"] for t in self.repo.ready_tasks(project_id=project_id, limit=5)]
        )
        for tid in candidatas:
            task = self.repo.claim(tid, self.worker, self.cfg.tasks.lease_seconds)
            if task is None:
                continue
            if task.get("requires_approval") and not _approved(self.repo, tid):
                self.repo.set_status(tid, Status.WAITING_APPROVAL, actor=self.worker,
                                     detail="exige aprovação humana antes de executar")
                continue

            corpo, tokens, fontes, deps, decisoes = build_task_context(
                self.cfg, self.repo, task, budget
            )
            run_id = self.repo.start_run(
                tid, self.worker, task.get("agent"),
                hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16], tokens,
            )
            self.repo.save_context(
                tid, run_id, corpo,
                hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16], tokens, fontes,
            )
            self.repo.set_status(tid, Status.RUNNING, actor=self.worker)
            self.repo.log(tid, f"reivindicada por {self.worker}", run_id=run_id)
            return Delivery(
                task=task, run_id=run_id, context=corpo, context_tokens=tokens,
                sources=fontes, dependencies_done=deps, decisions=decisoes,
            )
        return None

    def release(self, task_id: str, reason: str = "") -> bool:
        run = self.repo.active_run(task_id)
        if run:
            self.repo.finish_run(int(run["id"]), "released")
        return self.repo.release(task_id, self.worker, reason)

    def report(
        self, task_id: str, result: dict[str, Any],
    ) -> tuple[Validation, dict[str, Any]]:
        """Recebe o resultado, valida e processa. Devolve (validação, estado)."""
        t0 = time.perf_counter()
        task = self.repo.get(task_id)
        if task is None:
            raise KeyError(task_id)
        run = self.repo.active_run(task_id)
        run_id = int(run["id"]) if run else None

        res = TaskResult.from_dict(result)
        v = validate(self.cfg, task, res)
        self.repo.save_result(task_id, run_id, res.to_dict(), v.ok)

        if v.ok and res.status == "completed":
            estado = self._complete(task, res, run_id)
        else:
            motivo = "; ".join(v.failures) or f"agente reportou status '{res.status}'"
            estado = self._fail(task, motivo, run_id, kind=(
                "validation" if not v.ok else "execution"
            ))

        if run_id:
            self.repo.finish_run(
                run_id, "completed" if v.ok else "failed",
                int((time.perf_counter() - t0) * 1000),
            )
        return v, estado

    def _complete(
        self, task: dict[str, Any], res: TaskResult, run_id: int | None,
    ) -> dict[str, Any]:
        tid = task["id"]
        for arquivo in res.files_changed[:50]:
            self.repo.artifact(tid, run_id, "file", arquivo)

        # Decisão descoberta durante a execução vira registro — é o que faz a
        # próxima tarefa receber a restrição sem ninguém lembrar de contar.
        for d in res.decisions[:10]:
            if not isinstance(d, dict) or not d.get("title"):
                continue
            did = f"{task['project_id']}-D{abs(hash(d['title'])) % 9973:04d}"
            self.repo.add_decision(
                did, d["title"], project_id=task["project_id"], task_id=tid,
                context=str(d.get("context", "")), problem=str(d.get("problem", "")),
                options=list(d.get("options", [])),
                decision=str(d.get("decision", "")),
                consequences=str(d.get("consequences", "")),
            )

        self.repo.set_status(tid, Status.COMPLETED, actor=self.worker,
                             detail=res.summary[:200])
        liberadas = self.repo.promote_ready(task["project_id"])
        self.repo.event(EventType.TASK_COMPLETED, task_id=tid,
                        project_id=task["project_id"], actor=self.worker,
                        detail=f"liberou {len(liberadas)}")
        if res.knowledge_updates:
            self.repo.event(EventType.KNOWLEDGE_UPDATED, task_id=tid,
                            project_id=task["project_id"],
                            detail="; ".join(res.knowledge_updates[:3]))
        return {"status": "completed", "unblocked": liberadas}

    def _fail(
        self, task: dict[str, Any], motivo: str, run_id: int | None, kind: str,
    ) -> dict[str, Any]:
        tid = task["id"]
        self.repo.error(tid, run_id, kind, motivo)
        self.repo.set_status(tid, Status.FAILED, actor=self.worker, detail=motivo[:200])

        # Resultado inválido raramente melhora ao repetir a MESMA execução, mas
        # o agente pode corrigir e reenviar — então o retry existe; o que muda
        # é a causa registrada, para que o padrão apareça no histórico.
        pode = self.repo.schedule_retry(tid, list(self.cfg.tasks.backoff), motivo)
        if pode:
            self.repo.set_status(tid, Status.RETRYING, actor=self.worker)
            return {"status": "retrying", "reason": motivo,
                    "retry_count": (self.repo.get(tid) or {}).get("retry_count", 0)}
        return {"status": "failed", "reason": motivo, "retries_exhausted": True}


def _approved(repo: TaskRepository, task_id: str) -> bool:
    row = repo.conn.execute(
        "SELECT granted FROM approvals WHERE task_id = ? AND granted = 1 LIMIT 1",
        (task_id,),
    ).fetchone()
    return row is not None


# ── validação ───────────────────────────────────────────────────────────
def validate(cfg: Config, task: dict[str, Any], res: TaskResult) -> Validation:
    """Checagens determinísticas. Zero juízo sobre qualidade de código."""
    v = Validation()

    if not res.summary.strip():
        v.fail("resultado sem `summary`")

    criterios = task.get("acceptance_criteria") or []
    if criterios:
        marcados = {k for k, val in res.acceptance.items() if str(val).strip()}
        faltando = [c for c in criterios if c not in marcados]
        if faltando:
            v.fail(
                f"{len(faltando)} critério(s) de aceite sem evidência: "
                + "; ".join(f"«{c[:60]}»" for c in faltando[:3])
            )

    if task.get("test_requirements") and not res.tests:
        v.fail("a tarefa exige teste e o resultado não declara nenhum")

    escopo = task.get("files_scope") or []
    if escopo and res.files_changed:
        fora = [
            f for f in res.files_changed
            if not any(_within(f, p) for p in escopo)
        ]
        if fora:
            v.fail(
                "arquivo(s) fora do escopo declarado: "
                + ", ".join(f"`{f}`" for f in fora[:5])
            )

    # A verificação que importa mais: o gate não pode ser contornado por um
    # resultado que afirma ter mexido num arquivo bloqueado.
    bloqueados = _blocked(cfg, res.files_changed)
    if bloqueados:
        v.fail(
            "arquivo(s) bloqueados pelo Security Gate no resultado: "
            + ", ".join(f"`{b}`" for b in bloqueados[:5])
        )

    faltam_indice = _not_indexed(cfg, res.files_changed)
    if faltam_indice:
        v.warnings.append(
            f"{len(faltam_indice)} arquivo(s) declarados não estão no índice; "
            "rode `ragx index .` antes de validar"
        )
    return v


def _within(caminho: str, prefixo: str) -> bool:
    c = caminho.replace("\\", "/").lstrip("./")
    p = prefixo.replace("\\", "/").lstrip("./").rstrip("/")
    return c == p or c.startswith(p + "/")


def _blocked(cfg: Config, arquivos: list[str]) -> list[str]:
    if not arquivos or not cfg.db_path.exists():
        return []
    try:
        from ragx.storage.db import open_db

        with open_db(cfg.db_path, read_only=True) as conn:
            marcados = {
                r["rel_path"]
                for r in conn.execute(
                    "SELECT DISTINCT rel_path FROM security_events"
                )
            }
    except Exception:
        return []
    return [a for a in arquivos if a.replace("\\", "/") in marcados]


def _not_indexed(cfg: Config, arquivos: list[str]) -> list[str]:
    if not arquivos or not cfg.db_path.exists():
        return []
    try:
        from ragx.storage.db import open_db

        with open_db(cfg.db_path, read_only=True) as conn:
            conhecidos = {
                r["rel_path"] for r in conn.execute("SELECT rel_path FROM documents")
            }
    except Exception:
        return []
    return [a for a in arquivos if a.replace("\\", "/") not in conhecidos]


def result_from_json(texto: str) -> dict[str, Any]:
    data = json.loads(texto)
    if not isinstance(data, dict):
        raise ValueError("resultado precisa ser um objeto JSON")
    return data

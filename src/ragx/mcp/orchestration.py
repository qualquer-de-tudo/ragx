"""Ferramentas MCP de orquestração — o contrato entre o RAGX e o agente.

O RAGX é a fila e o árbitro; o agente é o executor (ADR-0015). Este módulo é a
única superfície por onde o agente reivindica trabalho e devolve resultado.

As invariantes do ADR-0006 valem aqui sem exceção: nada de `os`, `pathlib`,
`subprocess`, rede ou `open`. Tudo é delegado aos serviços — os mesmos que a
CLI chama, para que humano e agente nunca consigam coisas diferentes.
"""

from __future__ import annotations

from typing import Any

from ragx.config import Config
from ragx.mcp.tools import cap, err, ok, safe_echo
from ragx.tasks.dispatcher import TaskDispatcher
from ragx.tasks.models import DependencyKind, InvalidTransitionError, Status
from ragx.tasks.store import TaskRepository, open_tasks_db

_MAX_TASKS = 200


class OrchestrationAPI:
    """Fachada de tarefas. Leitura sempre; escrita só com `enabled`."""

    def __init__(self, cfg: Config, enabled: bool):
        self.cfg = cfg
        self.enabled = enabled
        # Identidade do worker: é o que o lease registra e o que permite saber
        # QUEM está com a tarefa quando algo trava.
        self.worker = cfg.tasks.worker_id or "mcp-agent"

    def _check(self) -> dict[str, Any] | None:
        if not self.enabled:
            return err(
                "write_disabled",
                "este servidor está em modo somente-leitura. "
                "Suba com `ragx mcp serve --write` ou defina [mcp] allow_write = true.",
            )
        return None

    # ── leitura ─────────────────────────────────────────────────────────
    def analyze_request(self, request: str) -> dict[str, Any]:
        """Classifica a solicitação. Não escreve nada, em lugar nenhum."""
        from ragx.tasks.service import analyze_request as run

        if not (request or "").strip():
            return err("invalid_request", "solicitação vazia")
        a = run(self.cfg, request)
        return ok(a.to_dict())

    def plan_work(self, request: str, apply: bool = False) -> dict[str, Any]:
        """Monta o plano. `apply=true` cria projeto, documentos e tarefas."""
        if apply:
            blocked = self._check()
            if blocked:
                return blocked
        from ragx.tasks.service import plan_work as run

        if not (request or "").strip():
            return err("invalid_request", "solicitação vazia")
        try:
            p = run(self.cfg, request, apply=apply)
        except ValueError as exc:
            return err("conflict", str(exc))
        return cap(ok(p.to_dict()), self.cfg.mcp.max_response_bytes)

    def list_tasks(
        self, project_id: str | None = None, status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        limite = max(1, min(int(limit), _MAX_TASKS))
        with open_tasks_db(self.cfg, read_only=True) as conn:
            tarefas = TaskRepository(conn).list_tasks(project_id, status, limite)
        return cap(
            ok({"tasks": [_slim(t) for t in tarefas], "count": len(tarefas)}),
            self.cfg.mcp.max_response_bytes,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        with open_tasks_db(self.cfg, read_only=True) as conn:
            repo = TaskRepository(conn)
            t = repo.get(task_id)
            if t is None:
                return err("not_found", f"tarefa não encontrada: {safe_echo(task_id, 48)}")
            deps = repo.dependencies_of(task_id)
            dependentes = repo.dependents_of(task_id)
            resultado = repo.latest_result(task_id)
        return cap(
            ok({
                "task": t, "dependencies": deps, "dependents": dependentes,
                "last_result": (resultado or {}).get("payload"),
            }),
            self.cfg.mcp.max_response_bytes,
        )

    def task_graph(self, project_id: str | None = None) -> dict[str, Any]:
        with open_tasks_db(self.cfg, read_only=True) as conn:
            repo = TaskRepository(conn)
            tarefas = repo.list_tasks(project_id=project_id, limit=_MAX_TASKS)
            arestas = repo.edges(project_id)
        return cap(
            ok({
                "nodes": [
                    {"id": t["id"], "title": t["title"], "status": t["status"],
                     "track": t["track"]}
                    for t in tarefas
                ],
                "edges": [{"from": a, "to": b, "kind": k} for a, b, k in arestas],
            }),
            self.cfg.mcp.max_response_bytes,
        )

    def next_task(self, project_id: str | None = None) -> dict[str, Any]:
        """A próxima executável — SEM reivindicar. Para decidir antes de pegar."""
        with open_tasks_db(self.cfg, read_only=True) as conn:
            t = TaskDispatcher(self.cfg, TaskRepository(conn)).next(project_id)
        if t is None:
            return ok({"task": None, "reason": "nenhuma tarefa pronta"})
        return ok({"task": _slim(t)})

    def task_status(self) -> dict[str, Any]:
        from ragx.tasks.service import status_panel

        return cap(ok(status_panel(self.cfg)), self.cfg.mcp.max_response_bytes)

    # ── escrita ─────────────────────────────────────────────────────────
    def claim_task(
        self, task_id: str | None = None, project_id: str | None = None,
        tokens: int | None = None,
    ) -> dict[str, Any]:
        """Reivindica com lease e devolve a tarefa COM o contexto pronto.

        O agente não remonta o contexto: ele recebe o pacote já dentro do
        orçamento de tokens, com as fontes. Deixar isso para o agente é como o
        contexto vira o repositório inteiro.
        """
        blocked = self._check()
        if blocked:
            return blocked
        with open_tasks_db(self.cfg) as conn:
            repo = TaskRepository(conn)
            d = TaskDispatcher(self.cfg, repo, self.worker).claim(
                task_id, project_id, tokens or self.cfg.tasks.context_tokens
            )
            conn.commit() if conn.in_transaction else None
        if d is None:
            return err(
                "unavailable",
                "nenhuma tarefa disponível: ou a fila está vazia, ou a tarefa "
                "pedida já foi reivindicada por outro. Use next_task para ver "
                "o que está pronto.",
            )
        return cap(ok(d.to_dict()), self.cfg.mcp.max_response_bytes)

    def report_task_result(
        self, task_id: str, result: dict[str, Any],
    ) -> dict[str, Any]:
        """Entrega o resultado; dispara validação e liberação das dependentes."""
        blocked = self._check()
        if blocked:
            return blocked
        if not isinstance(result, dict):
            return err("invalid_result", "result precisa ser um objeto")
        with open_tasks_db(self.cfg) as conn:
            repo = TaskRepository(conn)
            if repo.get(task_id) is None:
                return err("not_found", f"tarefa não encontrada: {safe_echo(task_id, 48)}")
            v, estado = TaskDispatcher(self.cfg, repo, self.worker).report(
                task_id, result
            )
            conn.commit() if conn.in_transaction else None
        return ok({
            "valid": v.ok, "failures": v.failures, "warnings": v.warnings,
            "state": estado,
        })

    def release_task(self, task_id: str, reason: str = "") -> dict[str, Any]:
        """Devolve a tarefa sem executar — o agente desistiu ou foi interrompido."""
        blocked = self._check()
        if blocked:
            return blocked
        with open_tasks_db(self.cfg) as conn:
            repo = TaskRepository(conn)
            soltou = TaskDispatcher(self.cfg, repo, self.worker).release(
                task_id, safe_echo(reason, 200)
            )
            conn.commit() if conn.in_transaction else None
        if not soltou:
            return err(
                "not_claimed",
                "esta tarefa não está reivindicada por você — nada foi alterado",
            )
        return ok({"task_id": task_id, "status": "ready"})

    def set_task_status(
        self, task_id: str, status: str, reason: str = "",
    ) -> dict[str, Any]:
        """Bloquear, desbloquear, cancelar. A matriz de transições é respeitada."""
        blocked = self._check()
        if blocked:
            return blocked
        try:
            novo = Status(status)
        except ValueError:
            validos = ", ".join(s.value for s in Status)
            return err("invalid_status", f"estado inválido; use um de: {validos}")
        with open_tasks_db(self.cfg) as conn:
            repo = TaskRepository(conn)
            if repo.get(task_id) is None:
                return err("not_found", f"tarefa não encontrada: {safe_echo(task_id, 48)}")
            try:
                repo.set_status(task_id, novo, actor=self.worker,
                                detail=safe_echo(reason, 200))
            except InvalidTransitionError as exc:
                return err("invalid_transition", str(exc))
            conn.commit() if conn.in_transaction else None
        return ok({"task_id": task_id, "status": str(novo)})

    def add_task_dependency(
        self, task_id: str, depends_on: str, kind: str = "depends_on",
    ) -> dict[str, Any]:
        blocked = self._check()
        if blocked:
            return blocked
        from ragx.tasks.models import CycleError

        try:
            tipo = DependencyKind(kind)
        except ValueError:
            validos = ", ".join(k.value for k in DependencyKind)
            return err("invalid_kind", f"tipo inválido; use um de: {validos}")
        with open_tasks_db(self.cfg) as conn:
            repo = TaskRepository(conn)
            try:
                repo.add_dependency(task_id, depends_on, tipo)
            except CycleError as exc:
                return err("cycle", str(exc))
            conn.commit() if conn.in_transaction else None
        return ok({"task_id": task_id, "depends_on": depends_on, "kind": str(tipo)})

    def run_worker(self) -> dict[str, Any]:
        """Um ciclo do worker: lease, promoção, retry, agendamento.

        Não executa tarefa — mantém a fila correta para que o agente encontre
        trabalho pronto.
        """
        blocked = self._check()
        if blocked:
            return blocked
        from ragx.tasks.worker import work

        return ok(work(self.cfg).to_dict())


def _slim(t: dict[str, Any]) -> dict[str, Any]:
    """Só o que o agente precisa para decidir. Menos ruído, menos tokens."""
    return {
        "id": t["id"], "project_id": t["project_id"], "title": t["title"],
        "status": t["status"], "priority": t["priority"], "track": t["track"],
        "type": t["type"], "requires_approval": t.get("requires_approval", False),
        "acceptance_criteria": t.get("acceptance_criteria", []),
        "files_scope": t.get("files_scope", []),
        "retry_count": t.get("retry_count", 0),
    }

"""Persistência da orquestração. O único módulo que escreve SQL de tarefa.

Banco próprio, `.ragx/ragx.sqlite`, separado do `knowledge.db` (ADR-0014):
`ragx vacuum` roda `VACUUM`, que bloqueia o banco inteiro — com os dois juntos,
ou o vacuum falha ou o worker trava. E `ragx reset` apaga `.ragx/` para
reconstruir o índice, o que é seguro porque o índice é derivado; o histórico de
execução não é.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.core.errors import EnvError
from ragx.tasks.models import (
    BLOCKING_KINDS,
    PRIORITY_RANK,
    SATISFYING,
    CycleError,
    DependencyKind,
    EventType,
    InvalidTransitionError,
    Status,
    Task,
    can_transition,
)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_NAME = "ragx.sqlite"

_PRAGMAS = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
    # Generoso de propósito: o worker e uma sessão MCP disputam o mesmo arquivo,
    # e esperar meio segundo é melhor que devolver erro ao agente.
    ("busy_timeout", "10000"),
)


def db_path(cfg: Config) -> Path:
    return cfg.state_dir / DB_NAME


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plus(seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path, read_only: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if read_only:
        if not path.exists():
            raise EnvError(f"banco de tarefas não encontrado: {path}")
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    for key, value in _PRAGMAS:
        if read_only and key in ("journal_mode", "synchronous"):
            continue
        conn.execute(f"PRAGMA {key} = {value}")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Sequência de migrações PRÓPRIA — `user_version` independente do knowledge.db."""
    atual = int(conn.execute("PRAGMA user_version").fetchone()[0])
    arquivos = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    aplicadas = 0
    for f in arquivos:
        versao = int(f.name[:4])
        if versao <= atual:
            continue
        # Sem `BEGIN` em volta: `executescript` emite um COMMIT implícito antes
        # de rodar, e envolver os dois faz o COMMIT seguinte falhar com
        # "no transaction is active". Toda instrução do arquivo é
        # `CREATE ... IF NOT EXISTS`, então reaplicar é inofensivo — e a
        # `user_version` só avança depois que o script inteiro passou.
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {versao}")
        aplicadas += 1
    return aplicadas


@contextmanager
def open_tasks_db(cfg: Config, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path(cfg), read_only=read_only)
    try:
        if not read_only:
            migrate(conn)
        yield conn
    finally:
        conn.close()


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _u(s: str | None, default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


class TaskRepository:
    """Toda escrita de tarefa passa por aqui, inclusive as transições."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ── projetos ────────────────────────────────────────────────────────
    def create_project(
        self, project_id: str, name: str, request: str, analysis: dict[str, Any],
        max_concurrency: int = 1,
    ) -> str:
        agora = utcnow()
        self.conn.execute(
            """INSERT INTO projects(id, name, request, classification, complexity,
                                    strategy, analysis_json, max_concurrency,
                                    created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (project_id, name, request, analysis.get("classification", "UNKNOWN"),
             analysis.get("complexity", "low"), analysis.get("strategy", "EXECUTE"),
             _j(analysis), max_concurrency, agora, agora),
        )
        self.event(EventType.TASK_CREATED, project_id=project_id,
                   detail=f"projeto criado: {name}")
        return project_id

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_projects(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM projects"
        args: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self.conn.execute(sql, args)]

    def set_project_status(self, project_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (status, utcnow(), project_id),
        )

    # ── tarefas ─────────────────────────────────────────────────────────
    def create_task(self, task: Task) -> str:
        if not task.acceptance_criteria:
            raise ValueError(
                f"{task.id}: tarefa sem critério de aceite. Sem isso não há como "
                f"validar o resultado, e `completed` não significaria nada."
            )
        agora = utcnow()
        self.conn.execute(
            """INSERT INTO tasks(
                   id, project_id, parent_task_id, seq, title, description, type,
                   track, status, priority, priority_rank, complexity,
                   acceptance_criteria, required_context, required_skills,
                   files_scope, security_requirements, performance_requirements,
                   test_requirements, agent, requires_approval, max_retries,
                   created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task.id, task.project_id, task.parent_task_id, task.seq, task.title,
             task.description, task.type, task.track, str(task.status),
             task.priority, PRIORITY_RANK.get(task.priority, 1), task.complexity,
             _j(task.acceptance_criteria), _j(task.required_context),
             _j(task.required_skills), _j(task.files_scope),
             _j(task.security_requirements), _j(task.performance_requirements),
             _j(task.test_requirements), task.agent, int(task.requires_approval),
             task.max_retries, agora, agora),
        )
        self.event(EventType.TASK_CREATED, task_id=task.id,
                   project_id=task.project_id, detail=task.title)
        return task.id

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._hydrate(row) if row else None

    def list_tasks(
        self, project_id: str | None = None, status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM tasks"
        cond, args = [], []
        if project_id:
            cond.append("project_id = ?")
            args.append(project_id)
        if status:
            cond.append("status = ?")
            args.append(status)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY priority_rank DESC, seq ASC LIMIT ?"
        args.append(limit)
        return [self._hydrate(r) for r in self.conn.execute(sql, args)]

    def _hydrate(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for campo in ("acceptance_criteria", "required_context", "required_skills",
                      "files_scope", "security_requirements",
                      "performance_requirements", "test_requirements"):
            d[campo] = _u(d.get(campo), [])
        d["requires_approval"] = bool(d.get("requires_approval"))
        return d

    # ── transições ──────────────────────────────────────────────────────
    def set_status(
        self, task_id: str, novo: Status, actor: str = "system", detail: str = "",
    ) -> None:
        """Toda mudança de estado passa aqui — e é validada contra a matriz.

        Espalhar `UPDATE tasks SET status` pelo código faria a máquina de estados
        existir só na documentação.
        """
        row = self.conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError(task_id)
        atual = Status(row["status"])
        if not can_transition(atual, novo):
            raise InvalidTransitionError(task_id, atual, novo)
        if atual == novo:
            return

        extra, args = "", []
        if novo is Status.RUNNING:
            extra, args = ", started_at = ?", [utcnow()]
        elif novo in (Status.COMPLETED, Status.CANCELLED, Status.SKIPPED):
            extra, args = ", completed_at = ?, locked_by = NULL, locked_at = NULL, lock_expires_at = NULL", [utcnow()]
        elif novo in (Status.READY, Status.PENDING):
            extra = ", locked_by = NULL, locked_at = NULL, lock_expires_at = NULL"

        self.conn.execute(
            f"UPDATE tasks SET status = ?, updated_at = ?{extra} WHERE id = ?",
            [str(novo), utcnow(), *args, task_id],
        )
        self.event(
            _event_for(novo), task_id=task_id, from_state=str(atual),
            to_state=str(novo), actor=actor, detail=detail,
        )

    def restore_status(self, task_id: str, status: Status, actor: str = "sync") -> None:
        """Grava o estado SEM passar pela matriz de transições.

        Reidratar do Git não é uma transição: é restaurar um estado que já
        aconteceu, possivelmente em outra máquina. `pending -> completed` é
        inválido durante a execução — e é exatamente o que um `git pull` traz
        quando o colega concluiu a tarefa. Aplicar a matriz aqui faria o board
        voltar errado e em silêncio.
        """
        extra = ""
        if status in (Status.COMPLETED, Status.CANCELLED, Status.SKIPPED):
            extra = ", completed_at = COALESCE(completed_at, ?)"
            args: list[Any] = [utcnow()]
        else:
            args = []
        self.conn.execute(
            f"""UPDATE tasks SET status = ?, updated_at = ?{extra},
                    locked_by = NULL, locked_at = NULL, lock_expires_at = NULL
                  WHERE id = ?""",
            [str(status), utcnow(), *args, task_id],
        )
        self.event(EventType.TASK_READY, task_id=task_id, to_state=str(status),
                   actor=actor, detail="restaurado")

    # ── dependências ────────────────────────────────────────────────────
    def add_dependency(
        self, task_id: str, depends_on: str,
        kind: DependencyKind = DependencyKind.DEPENDS_ON,
    ) -> None:
        if task_id == depends_on:
            raise CycleError([task_id, task_id])
        if kind in BLOCKING_KINDS:
            caminho = self._would_cycle(task_id, depends_on)
            if caminho:
                raise CycleError(caminho)
        self.conn.execute(
            """INSERT OR IGNORE INTO task_dependencies(task_id, depends_on_task_id,
                                                       kind, created_at)
               VALUES(?,?,?,?)""",
            (task_id, depends_on, str(kind), utcnow()),
        )

    def _would_cycle(self, task_id: str, depends_on: str) -> list[str]:
        """Ciclo é recusado na CRIAÇÃO, não descoberto na execução.

        Caminhar de `depends_on` para cima: se chegarmos em `task_id`, a aresta
        nova fecharia o laço. Devolve o caminho para a mensagem de erro — "existe
        um ciclo" sem dizer qual não ajuda ninguém.
        """
        pilha = [(depends_on, [task_id, depends_on])]
        visto = {depends_on}
        while pilha:
            atual, caminho = pilha.pop()
            for r in self.conn.execute(
                "SELECT depends_on_task_id FROM task_dependencies "
                "WHERE task_id = ? AND kind IN ({})".format(
                    ",".join("?" * len(BLOCKING_KINDS))
                ),
                (atual, *[str(k) for k in BLOCKING_KINDS]),
            ):
                prox = r["depends_on_task_id"]
                if prox == task_id:
                    return [*caminho, task_id]
                if prox not in visto:
                    visto.add(prox)
                    pilha.append((prox, [*caminho, prox]))
        return []

    def dependencies_of(self, task_id: str) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT d.depends_on_task_id AS id, d.kind, t.title, t.status
                     FROM task_dependencies d
                     JOIN tasks t ON t.id = d.depends_on_task_id
                    WHERE d.task_id = ?
                    ORDER BY t.seq""",
                (task_id,),
            )
        ]

    def dependents_of(self, task_id: str) -> list[str]:
        return [
            r["task_id"]
            for r in self.conn.execute(
                "SELECT task_id FROM task_dependencies "
                "WHERE depends_on_task_id = ? AND kind IN ({})".format(
                    ",".join("?" * len(BLOCKING_KINDS))
                ),
                (task_id, *[str(k) for k in BLOCKING_KINDS]),
            )
        ]

    def edges(self, project_id: str | None = None) -> list[tuple[str, str, str]]:
        sql = """SELECT d.task_id, d.depends_on_task_id, d.kind
                   FROM task_dependencies d JOIN tasks t ON t.id = d.task_id"""
        args: list[Any] = []
        if project_id:
            sql += " WHERE t.project_id = ?"
            args.append(project_id)
        return [
            (r["task_id"], r["depends_on_task_id"], r["kind"])
            for r in self.conn.execute(sql, args)
        ]

    # ── a fila ──────────────────────────────────────────────────────────
    def ready_tasks(
        self, project_id: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Tarefas executáveis, em UMA consulta.

        Buscar as pendentes e depois consultar as dependências de cada uma é o
        N+1 clássico: num board de 500 tarefas são 501 consultas por ciclo do
        worker. O `NOT EXISTS` resolve tudo de uma vez.
        """
        args: list[Any] = [*[str(k) for k in BLOCKING_KINDS],
                           *[str(s) for s in SATISFYING]]
        sql = """
            SELECT t.* FROM tasks t
             WHERE t.status IN ('pending','ready')
               AND NOT EXISTS (
                     SELECT 1 FROM task_dependencies d
                       JOIN tasks dep ON dep.id = d.depends_on_task_id
                      WHERE d.task_id = t.id
                        AND d.kind IN ({kinds})
                        AND dep.status NOT IN ({sat})
               )
        """.format(
            kinds=",".join("?" * len(BLOCKING_KINDS)),
            sat=",".join("?" * len(SATISFYING)),
        )
        if project_id:
            sql += " AND t.project_id = ?"
            args.append(project_id)
        sql += " ORDER BY t.priority_rank DESC, t.seq ASC LIMIT ?"
        args.append(limit)
        return [self._hydrate(r) for r in self.conn.execute(sql, args)]

    def promote_ready(self, project_id: str | None = None) -> list[str]:
        """`PENDING → READY` para quem teve as dependências fechadas."""
        promovidas = []
        for t in self.ready_tasks(project_id=project_id, limit=1000):
            if t["status"] == str(Status.PENDING):
                self.set_status(t["id"], Status.READY, actor="worker",
                                detail="dependências satisfeitas")
                promovidas.append(t["id"])
        return promovidas

    # ── lease ───────────────────────────────────────────────────────────
    def claim(
        self, task_id: str, worker: str, lease_seconds: int = 900,
    ) -> dict[str, Any] | None:
        """Reivindicação ATÔMICA. Devolve a tarefa ou None se outro ganhou.

        `SELECT` e depois `UPDATE` perde a corrida: entre os dois, outro processo
        passa. Aqui a condição está DENTRO do `UPDATE`, e quem ganhou é quem viu
        `rowcount == 1`. `BEGIN IMMEDIATE` adquire o bloqueio de escrita no
        começo, não no commit — sem isso, duas transações otimistas colidem no
        final e uma leva `SQLITE_BUSY`.
        """
        agora = utcnow()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self.conn.execute(
                """UPDATE tasks
                      SET status = 'queued', locked_by = ?, locked_at = ?,
                          lock_expires_at = ?, updated_at = ?
                    WHERE id = ?
                      AND status = 'ready'
                      AND (lock_expires_at IS NULL OR lock_expires_at < ?)""",
                (worker, agora, _plus(lease_seconds), agora, task_id, agora),
            )
            venceu = cur.rowcount == 1
            if venceu:
                self.conn.execute(
                    """INSERT INTO task_events(task_id, type, from_state, to_state,
                                               actor, detail, created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (task_id, str(EventType.TASK_CLAIMED), "ready", "queued",
                     worker, "", agora),
                )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get(task_id) if venceu else None

    def release(self, task_id: str, worker: str, reason: str = "") -> bool:
        cur = self.conn.execute(
            """UPDATE tasks
                  SET status = 'ready', locked_by = NULL, locked_at = NULL,
                      lock_expires_at = NULL, updated_at = ?
                WHERE id = ? AND locked_by = ? AND status IN ('queued','running')""",
            (utcnow(), task_id, worker),
        )
        if cur.rowcount:
            self.event(EventType.TASK_RELEASED, task_id=task_id, actor=worker,
                       detail=reason)
        return bool(cur.rowcount)

    def expire_leases(self) -> list[str]:
        """Agente que morreu no meio deixa a tarefa presa. Aqui ela volta.

        Sem isto, uma queda trava a fila para sempre — e o sintoma é "o board
        parou" sem nenhum erro em lugar nenhum.
        """
        agora = utcnow()
        presas = [
            r["id"]
            for r in self.conn.execute(
                """SELECT id FROM tasks
                    WHERE status IN ('queued','running')
                      AND lock_expires_at IS NOT NULL
                      AND lock_expires_at < ?""",
                (agora,),
            )
        ]
        for tid in presas:
            self.conn.execute(
                """UPDATE tasks SET status = 'ready', locked_by = NULL,
                       locked_at = NULL, lock_expires_at = NULL, updated_at = ?
                     WHERE id = ?""",
                (agora, tid),
            )
            self.error(tid, None, "lease_expired", "lease expirou; tarefa devolvida à fila")
            self.event(EventType.LEASE_EXPIRED, task_id=tid, to_state="ready",
                       actor="worker")
        return presas

    # ── runs, logs, resultados ──────────────────────────────────────────
    def start_run(
        self, task_id: str, worker: str, agent: str | None,
        context_hash: str | None, context_tokens: int,
    ) -> int:
        attempt = int(
            self.conn.execute(
                "SELECT COALESCE(MAX(attempt), 0) + 1 FROM task_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()[0]
        )
        cur = self.conn.execute(
            """INSERT INTO task_runs(task_id, attempt, status, agent, claimed_by,
                                     context_hash, context_tokens, started_at)
               VALUES(?,?,'running',?,?,?,?,?)""",
            (task_id, attempt, agent, worker, context_hash, context_tokens, utcnow()),
        )
        run_id = int(cur.lastrowid or 0)
        self.conn.execute(
            "INSERT INTO task_attempts(run_id, task_id, number, created_at) VALUES(?,?,?,?)",
            (run_id, task_id, attempt, utcnow()),
        )
        return run_id

    def finish_run(self, run_id: int, status: str, duration_ms: int | None = None) -> None:
        self.conn.execute(
            "UPDATE task_runs SET status = ?, finished_at = ?, duration_ms = ? WHERE id = ?",
            (status, utcnow(), duration_ms, run_id),
        )

    def active_run(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM task_runs WHERE task_id = ? AND status = 'running' "
            "ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def save_context(
        self, task_id: str, run_id: int | None, body: str, content_hash: str,
        tokens: int, sources: Iterable[str],
    ) -> None:
        self.conn.execute(
            """INSERT INTO task_context(task_id, run_id, content_hash, tokens,
                                        sources, body, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (task_id, run_id, content_hash, tokens, _j(list(sources)), body, utcnow()),
        )

    def save_result(
        self, task_id: str, run_id: int | None, payload: dict[str, Any],
        valid: bool | None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO task_results(task_id, run_id, status, summary, payload,
                                        valid, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (task_id, run_id, payload.get("status", "completed"),
             payload.get("summary", ""), _j(payload),
             None if valid is None else int(valid), utcnow()),
        )

    def latest_result(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM task_results WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["payload"] = _u(d["payload"], {})
        return d

    def log(self, task_id: str, message: str, level: str = "info",
            run_id: int | None = None) -> None:
        self.conn.execute(
            "INSERT INTO task_logs(task_id, run_id, level, message, created_at) "
            "VALUES(?,?,?,?,?)",
            (task_id, run_id, level, message, utcnow()),
        )

    def logs(self, task_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM task_logs WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                (task_id, limit),
            )
        ]

    def error(self, task_id: str, run_id: int | None, kind: str, message: str) -> None:
        self.conn.execute(
            "INSERT INTO task_errors(task_id, run_id, kind, message, created_at) "
            "VALUES(?,?,?,?,?)",
            (task_id, run_id, kind, message[:2000], utcnow()),
        )

    def artifact(self, task_id: str, run_id: int | None, kind: str, rel_path: str) -> None:
        self.conn.execute(
            "INSERT INTO task_artifacts(task_id, run_id, kind, rel_path, created_at) "
            "VALUES(?,?,?,?,?)",
            (task_id, run_id, kind, rel_path, utcnow()),
        )

    # ── retry ───────────────────────────────────────────────────────────
    def schedule_retry(self, task_id: str, backoff: list[int], error: str) -> bool:
        """Devolve True se ainda há tentativa. Nunca é infinito."""
        row = self.conn.execute(
            "SELECT retry_count, max_retries FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return False
        proximo = int(row["retry_count"]) + 1
        if proximo > int(row["max_retries"]):
            self.conn.execute(
                "UPDATE tasks SET last_error = ?, updated_at = ? WHERE id = ?",
                (error[:1000], utcnow(), task_id),
            )
            return False
        espera = backoff[min(proximo - 1, len(backoff) - 1)] if backoff else 60
        self.conn.execute(
            """UPDATE tasks SET retry_count = ?, last_error = ?, next_retry_at = ?,
                   updated_at = ? WHERE id = ?""",
            (proximo, error[:1000], _plus(espera), utcnow(), task_id),
        )
        return True

    def due_retries(self) -> list[str]:
        agora = utcnow()
        return [
            r["id"]
            for r in self.conn.execute(
                "SELECT id FROM tasks WHERE status = 'retrying' "
                "AND next_retry_at IS NOT NULL AND next_retry_at <= ?",
                (agora,),
            )
        ]

    # ── eventos ─────────────────────────────────────────────────────────
    def event(
        self, type_: EventType | str, task_id: str | None = None,
        project_id: str | None = None, from_state: str | None = None,
        to_state: str | None = None, actor: str = "system", detail: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO task_events(task_id, project_id, type, from_state,
                                       to_state, actor, detail, created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (task_id, project_id, str(type_), from_state, to_state, actor,
             detail[:500], utcnow()),
        )

    def events(self, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM task_events"
        args: list[Any] = []
        if task_id:
            sql += " WHERE task_id = ?"
            args.append(task_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args)]

    def unconsumed_events(self, limit: int = 200) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM task_events WHERE consumed = 0 ORDER BY id LIMIT ?",
                (limit,),
            )
        ]

    def consume_events(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        self.conn.execute(
            f"UPDATE task_events SET consumed = 1 WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )

    # ── documentos e decisões ───────────────────────────────────────────
    def add_document(
        self, doc_id: str, project_id: str, doc_type: str, title: str,
        rel_path: str, grounding: list[str], gaps: list[str],
        task_id: str | None = None,
    ) -> None:
        agora = utcnow()
        self.conn.execute(
            """INSERT OR REPLACE INTO knowledge_documents(
                   id, project_id, task_id, doc_type, title, rel_path, status,
                   grounding, gaps, created_at, updated_at)
               VALUES(?,?,?,?,?,?,'planned',?,?,?,?)""",
            (doc_id, project_id, task_id, doc_type, title, rel_path,
             _j(grounding), _j(gaps), agora, agora),
        )

    def documents(self, project_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM knowledge_documents"
        args: list[Any] = []
        if project_id:
            sql += " WHERE project_id = ?"
            args.append(project_id)
        sql += " ORDER BY doc_type, title"
        out = []
        for r in self.conn.execute(sql, args):
            d = dict(r)
            d["grounding"] = _u(d["grounding"], [])
            d["gaps"] = _u(d["gaps"], [])
            out.append(d)
        return out

    def add_decision(
        self, decision_id: str, title: str, project_id: str | None = None,
        task_id: str | None = None, context: str = "", problem: str = "",
        options: list[str] | None = None, decision: str = "",
        consequences: str = "", status: str = "proposed", rel_path: str | None = None,
    ) -> None:
        agora = utcnow()
        self.conn.execute(
            """INSERT OR REPLACE INTO decisions(
                   id, project_id, task_id, title, context, problem, options,
                   decision, consequences, status, rel_path, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (decision_id, project_id, task_id, title, context, problem,
             _j(options or []), decision, consequences, status, rel_path, agora, agora),
        )

    def decisions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM decisions"
        args: list[Any] = []
        if project_id:
            sql += " WHERE project_id = ?"
            args.append(project_id)
        sql += " ORDER BY created_at"
        out = []
        for r in self.conn.execute(sql, args):
            d = dict(r)
            d["options"] = _u(d["options"], [])
            out.append(d)
        return out

    # ── painel ──────────────────────────────────────────────────────────
    def counts(self, project_id: str | None = None) -> dict[str, int]:
        sql = "SELECT status, COUNT(*) n FROM tasks"
        args: list[Any] = []
        if project_id:
            sql += " WHERE project_id = ?"
            args.append(project_id)
        sql += " GROUP BY status"
        return {r["status"]: r["n"] for r in self.conn.execute(sql, args)}

    def next_task_id(self, project_id: str) -> tuple[str, int]:
        n = int(
            self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM tasks WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
        )
        return f"{project_id}-T{n:03d}", n


def _event_for(novo: Status) -> EventType:
    return {
        Status.READY: EventType.TASK_READY,
        Status.COMPLETED: EventType.TASK_COMPLETED,
        Status.FAILED: EventType.TASK_FAILED,
        Status.BLOCKED: EventType.TASK_BLOCKED,
        Status.CANCELLED: EventType.TASK_CANCELLED,
    }.get(novo, EventType.TASK_READY)

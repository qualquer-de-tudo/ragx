"""Worker e scheduler — mantêm a fila correta. Nunca executam tarefa.

O cron **só acorda** o RAGX (§15 do pedido). A inteligência está aqui, e o que
está aqui é transição de estado, não execução: quem executa é o agente
(ADR-0015).

Um ciclo é idempotente: rodar duas vezes seguidas não muda nada na segunda.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ragx.config import Config
from ragx.tasks.models import EventType, Status
from ragx.tasks.store import TaskRepository, open_tasks_db, utcnow


@dataclass
class WorkerReport:
    leases_expired: list[str] = field(default_factory=list)
    promoted: list[str] = field(default_factory=list)
    retried: list[str] = field(default_factory=list)
    schedules_fired: list[str] = field(default_factory=list)
    events_consumed: int = 0
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> int:
        return (
            len(self.leases_expired) + len(self.promoted)
            + len(self.retried) + len(self.schedules_fired)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "leases_expired": self.leases_expired, "promoted": self.promoted,
            "retried": self.retried, "schedules_fired": self.schedules_fired,
            "events_consumed": self.events_consumed, "errors": self.errors,
            "counts": self.counts, "changed": self.changed,
        }


def run_cycle(cfg: Config, repo: TaskRepository) -> WorkerReport:
    """Os seis passos. Falha num deles não derruba os outros.

    Um worker que morre no primeiro erro deixa a fila congelada sem nenhum
    sinal — o board simplesmente para, e ninguém descobre por dias.
    """
    r = WorkerReport()

    for nome, passo in (
        ("expirar leases", lambda: r.leases_expired.extend(repo.expire_leases())),
        ("promover prontas", lambda: r.promoted.extend(repo.promote_ready())),
        ("aplicar retries", lambda: r.retried.extend(_apply_retries(repo))),
        ("disparar agendamentos", lambda: r.schedules_fired.extend(_fire_schedules(repo))),
        ("consumir eventos", lambda: setattr(r, "events_consumed", _consume(repo))),
    ):
        try:
            passo()
        except Exception as exc:
            r.errors.append(f"{nome}: {type(exc).__name__}: {exc}")

    try:
        r.counts = repo.counts()
    except Exception as exc:
        r.errors.append(f"contagem: {exc}")
    return r


def work(cfg: Config) -> WorkerReport:
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        r = run_cycle(cfg, repo)
        conn.commit() if conn.in_transaction else None
    return r


def _apply_retries(repo: TaskRepository) -> list[str]:
    feitos = []
    for tid in repo.due_retries():
        repo.set_status(tid, Status.READY, actor="worker", detail="retry vencido")
        feitos.append(tid)
    return feitos


def _consume(repo: TaskRepository) -> int:
    """Eventos existem para a trilha de auditoria e para acordar dependentes.

    A promoção já aconteceu no passo 2; aqui só marcamos o que foi visto, para
    que a fila de eventos não cresça para sempre.
    """
    abertos = repo.unconsumed_events(limit=500)
    repo.consume_events([int(e["id"]) for e in abertos])
    return len(abertos)


# ── agendamento ─────────────────────────────────────────────────────────
def _fire_schedules(repo: TaskRepository) -> list[str]:
    agora = utcnow()
    disparados = []
    vencidos = repo.conn.execute(
        """SELECT * FROM schedules
            WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?""",
        (agora,),
    ).fetchall()
    for s in vencidos:
        sid = s["id"]
        repo.event(EventType.SCHEDULE_FIRED, task_id=s["task_id"],
                   project_id=s["project_id"], actor="scheduler", detail=sid)
        if s["task_id"]:
            atual = repo.get(s["task_id"])
            if atual and atual["status"] in (str(Status.PENDING), str(Status.BLOCKED)):
                # Agendamento que não consegue promover não derruba o ciclo: a
                # tarefa pode ter mudado de estado entre a consulta e aqui.
                with contextlib.suppress(Exception):
                    repo.set_status(s["task_id"], Status.READY, actor="scheduler")
        proximo = next_run(dict(s), depois=datetime.now(UTC))
        repo.conn.execute(
            "UPDATE schedules SET last_run_at = ?, next_run_at = ?, updated_at = ? "
            "WHERE id = ?",
            (agora, proximo, agora, sid),
        )
        disparados.append(sid)
    return disparados


def next_run(schedule: dict[str, Any], depois: datetime | None = None) -> str | None:
    """Próxima execução. `once` não tem próxima — e é isso que evita o laço."""
    base = depois or datetime.now(UTC)
    tipo = schedule.get("schedule_type", "cron")
    if tipo == "once":
        return None
    if tipo == "interval":
        segundos = int(schedule.get("interval_s") or 300)
        return (base + timedelta(seconds=segundos)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if tipo == "cron":
        expr = schedule.get("cron_expression") or "*/5 * * * *"
        return cron_next(expr, base).strftime("%Y-%m-%dT%H:%M:%SZ")
    # dependency, event e manual são disparados por outro caminho.
    return None


_CRON_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))


def parse_cron(expr: str) -> list[set[int]]:
    """Cron de 5 campos, sem dependência nova.

    Suporta `*`, `N`, `a-b`, `*/n`, `a-b/n` e listas com vírgula. É o
    subconjunto que cobre todo exemplo do pedido; qualquer coisa além disso é
    recusada com mensagem clara em vez de aceita e ignorada em silêncio.
    """
    campos = (expr or "").split()
    if len(campos) != 5:
        raise ValueError(
            f"expressão cron precisa de 5 campos (minuto hora dia mês dia-da-semana), "
            f"recebeu {len(campos)}: {expr!r}"
        )
    out: list[set[int]] = []
    for campo, (lo, hi) in zip(campos, _CRON_RANGES, strict=True):
        out.append(_parse_field(campo, lo, hi, expr))
    return out


def _parse_field(campo: str, lo: int, hi: int, expr: str) -> set[int]:
    valores: set[int] = set()
    for parte in campo.split(","):
        m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", parte.strip())
        if not m:
            raise ValueError(f"campo cron inválido {parte!r} em {expr!r}")
        alcance, passo_txt = m.group(1), m.group(2)
        passo = int(passo_txt) if passo_txt else 1
        if passo <= 0:
            raise ValueError(f"passo precisa ser positivo em {parte!r}")
        if alcance == "*":
            inicio, fim = lo, hi
        elif "-" in alcance:
            inicio, fim = (int(x) for x in alcance.split("-", 1))
        else:
            inicio = fim = int(alcance)
        if inicio < lo or fim > hi or inicio > fim:
            raise ValueError(
                f"campo cron fora da faixa [{lo}..{hi}]: {parte!r} em {expr!r}"
            )
        valores.update(range(inicio, fim + 1, passo))
    return valores


def cron_next(expr: str, base: datetime | None = None) -> datetime:
    """Próximo instante que casa. Busca por minuto, com teto de um ano."""
    campos = parse_cron(expr)
    minutos, horas, dias, meses, semanas = campos
    atual = (base or datetime.now(UTC)).replace(second=0, microsecond=0) + timedelta(
        minutes=1
    )
    limite = atual + timedelta(days=366)
    while atual <= limite:
        if (
            atual.minute in minutos
            and atual.hour in horas
            and atual.day in dias
            and atual.month in meses
            # cron usa 0=domingo; Python usa 0=segunda.
            and ((atual.weekday() + 1) % 7) in semanas
        ):
            return atual
        atual += timedelta(minutes=1)
    raise ValueError(f"expressão cron nunca dispara em um ano: {expr!r}")


def add_schedule(
    repo: TaskRepository, schedule_id: str, schedule_type: str,
    cron_expression: str | None = None, interval_s: int | None = None,
    project_id: str | None = None, task_id: str | None = None,
    event_type: str | None = None,
) -> str:
    if schedule_type == "cron" and cron_expression:
        parse_cron(cron_expression)  # valida agora, não na primeira execução
    agora = utcnow()
    proximo = next_run(
        {
            "schedule_type": schedule_type, "cron_expression": cron_expression,
            "interval_s": interval_s,
        }
    )
    if schedule_type == "once" and proximo is None:
        proximo = agora
    repo.conn.execute(
        """INSERT OR REPLACE INTO schedules(
               id, project_id, task_id, schedule_type, cron_expression,
               interval_s, event_type, next_run_at, enabled, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
        (schedule_id, project_id, task_id, schedule_type, cron_expression,
         interval_s, event_type, proximo, agora, agora),
    )
    return schedule_id


def list_schedules(repo: TaskRepository) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in repo.conn.execute("SELECT * FROM schedules ORDER BY next_run_at")
    ]


def set_schedule_enabled(repo: TaskRepository, schedule_id: str, enabled: bool) -> bool:
    cur = repo.conn.execute(
        "UPDATE schedules SET enabled = ?, updated_at = ? WHERE id = ?",
        (int(enabled), utcnow(), schedule_id),
    )
    return bool(cur.rowcount)


def remove_schedule(repo: TaskRepository, schedule_id: str) -> bool:
    cur = repo.conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    return bool(cur.rowcount)

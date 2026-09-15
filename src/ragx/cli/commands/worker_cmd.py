"""`ragx worker` e `ragx schedule` — o motor que mantém a fila correta.

O worker NÃO executa tarefa. Ele expira lease, promove o que ficou pronto,
aplica retry e dispara agendamento; quem executa é o agente (ADR-0015).
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ragx.config import load_config
from ragx.core.errors import UsageError
from ragx.tasks import worker as wk
from ragx.tasks.store import TaskRepository, open_tasks_db

console = Console()
app = typer.Typer(help="Agendamentos de disparo.", no_args_is_help=True)


def worker(
    once: Annotated[bool, typer.Option("--once", help="Um ciclo e sai. É o modo do cron.")] = True,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Executa um ciclo de manutenção da fila.

    Pensado para cron:

        */5 * * * * cd /caminho/do/projeto && ragx worker

    Não executa tarefa nenhuma — mantém a fila pronta para que o agente
    encontre trabalho.
    """
    cfg = load_config()
    if not once:
        raise UsageError(
            "modo contínuo não existe de propósito: use cron ou um laço do seu "
            "supervisor. `ragx worker` já é um ciclo completo."
        )
    r = wk.work(cfg)
    if as_json:
        console.print_json(json.dumps(r.to_dict(), ensure_ascii=False))
        return

    console.print("\n[bold]worker[/]")
    linhas = (
        ("leases expirados", r.leases_expired, "yellow"),
        ("promovidas a ready", r.promoted, "green"),
        ("retries aplicados", r.retried, "cyan"),
        ("agendamentos disparados", r.schedules_fired, "cyan"),
    )
    for rotulo, itens, cor in linhas:
        if itens:
            curtos = ", ".join(x.rsplit("-", 1)[-1] for x in itens[:6])
            console.print(f"  [{cor}]{len(itens):>3}[/] {rotulo}  [dim]{curtos}[/]")
    if not r.changed:
        console.print("  [dim]nada a fazer[/]")
    for e in r.errors:
        console.print(f"  [red]![/] {e}")
    if r.counts:
        resumo = " · ".join(f"{k} {v}" for k, v in sorted(r.counts.items()))
        console.print(f"\n  [dim]{resumo}[/]")
    console.print()


@app.command("list")
def list_cmd(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Agendamentos registrados."""
    cfg = load_config()
    with open_tasks_db(cfg, read_only=True) as conn:
        agendas = wk.list_schedules(TaskRepository(conn))
    if as_json:
        console.print_json(json.dumps(agendas, ensure_ascii=False, default=str))
        return
    if not agendas:
        console.print(
            "\n[dim]nenhum agendamento.[/]"
            '\n  [bold]ragx schedule add diario --type cron --cron "0 2 * * *"[/]\n'
        )
        return
    t = Table(box=None, pad_edge=False)
    for col in ("id", "tipo", "expressão", "próxima", "ativo"):
        t.add_column(col)
    for s in agendas:
        t.add_row(
            s["id"], s["schedule_type"],
            s["cron_expression"] or (f"{s['interval_s']}s" if s["interval_s"] else "—"),
            s["next_run_at"] or "—",
            "sim" if s["enabled"] else "[dim]não[/]",
        )
    console.print()
    console.print(t)
    console.print()


@app.command("add")
def add_cmd(
    schedule_id: Annotated[str, typer.Argument(help="Nome do agendamento.")],
    type_: Annotated[str, typer.Option("--type", help="once|cron|interval|dependency|event|manual")] = "cron",
    cron: Annotated[str | None, typer.Option("--cron", help='Ex.: "*/5 * * * *"')] = None,
    interval: Annotated[int | None, typer.Option("--interval", help="Segundos.")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    task: Annotated[str | None, typer.Option("--task")] = None,
    event: Annotated[str | None, typer.Option("--event")] = None,
) -> None:
    """Cria um agendamento. A expressão cron é validada agora, não na 1ª execução."""
    cfg = load_config()
    if type_ == "cron" and not cron:
        raise UsageError('--cron é obrigatório para --type cron (ex.: "*/5 * * * *")')
    if type_ == "interval" and not interval:
        raise UsageError("--interval em segundos é obrigatório para --type interval")
    try:
        with open_tasks_db(cfg) as conn:
            repo = TaskRepository(conn)
            wk.add_schedule(
                repo, schedule_id, type_, cron_expression=cron, interval_s=interval,
                project_id=project, task_id=task, event_type=event,
            )
            agendas = {s["id"]: s for s in wk.list_schedules(repo)}
            conn.commit() if conn.in_transaction else None
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    proximo = agendas.get(schedule_id, {}).get("next_run_at") or "—"
    console.print(f"\n[green]✓[/] [bold]{schedule_id}[/] ({type_})  próxima: {proximo}\n")


@app.command("remove")
def remove_cmd(schedule_id: Annotated[str, typer.Argument()]) -> None:
    """Remove um agendamento."""
    cfg = load_config()
    with open_tasks_db(cfg) as conn:
        ok = wk.remove_schedule(TaskRepository(conn), schedule_id)
        conn.commit() if conn.in_transaction else None
    if not ok:
        raise UsageError(f"agendamento não encontrado: {schedule_id}")
    console.print(f"\n[green]✓[/] {schedule_id} removido\n")


@app.command("enable")
def enable_cmd(schedule_id: Annotated[str, typer.Argument()]) -> None:
    """Reativa um agendamento."""
    _toggle(schedule_id, True)


@app.command("disable")
def disable_cmd(schedule_id: Annotated[str, typer.Argument()]) -> None:
    """Desativa sem remover."""
    _toggle(schedule_id, False)


def _toggle(schedule_id: str, enabled: bool) -> None:
    cfg = load_config()
    with open_tasks_db(cfg) as conn:
        ok = wk.set_schedule_enabled(TaskRepository(conn), schedule_id, enabled)
        conn.commit() if conn.in_transaction else None
    if not ok:
        raise UsageError(f"agendamento não encontrado: {schedule_id}")
    console.print(
        f"\n[green]✓[/] {schedule_id} {'ativado' if enabled else 'desativado'}\n"
    )

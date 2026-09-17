"""`ragx task` — analisar, planejar, acompanhar e validar trabalho."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from ragx.config import load_config
from ragx.core.errors import UsageError
from ragx.security.redactor import safe_echo

if TYPE_CHECKING:
    from ragx.tasks.models import Status

console = Console()
app = typer.Typer(help="Análise, planejamento e execução de trabalho.", no_args_is_help=True)

_CORES = {
    "pending": "dim", "ready": "cyan", "queued": "yellow", "running": "bold yellow",
    "blocked": "red", "waiting_approval": "magenta", "failed": "bold red",
    "retrying": "yellow", "completed": "green", "cancelled": "dim",
    "skipped": "dim",
}


def _repo(read_only: bool = False):
    from ragx.tasks.store import open_tasks_db

    cfg = load_config()
    return cfg, open_tasks_db(cfg, read_only=read_only)


def _conn(read_only: bool = True):
    """Só a conexão, para os comandos que não precisam da config."""
    return _repo(read_only)[1]


@app.command("analyze")
def analyze_cmd(
    request: Annotated[str, typer.Argument(help="A solicitação, em texto livre.")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Classifica a solicitação. NÃO escreve nada."""
    from ragx.tasks import service

    cfg = load_config()
    a = service.analyze_request(cfg, request)
    if as_json:
        console.print_json(json.dumps(a.to_dict(), ensure_ascii=False))
        return

    console.print(f'\n[bold]Análise[/] — "{safe_echo(request, 70)}"\n')
    console.print(f"  Classificação   [bold]{a.classification.value}[/]")
    console.print(f"  Complexidade    {a.complexity}          Confiança  {a.confidence}")
    console.print(f"  Estratégia      [bold cyan]{a.strategy}[/]")
    if a.requires_approval:
        console.print("  [magenta]Exige aprovação humana antes de executar[/]")
    console.print()

    rotulos = {
        "architecture": "arquitetura", "complexity": "complexidade",
        "dependency": "dependência", "security": "segurança", "risk": "risco",
        "business_rule": "regra", "documentation": "documentação",
    }
    for chave, valor in sorted(
        a.scores.as_dict().items(), key=lambda kv: -kv[1]
    ):
        barra = "█" * int(valor / 8)
        cor = "red" if valor >= 60 else ("yellow" if valor >= 35 else "dim")
        console.print(f"  {rotulos[chave]:<14} [{cor}]{valor:>3}  {barra}[/]")
    console.print(f"\n  [dim]total efetivo {a.total}[/]")
    console.print(f"\n  Por quê         [dim]{a.reasoning_summary}[/]")
    if a.dependencies:
        console.print("\n  Já toca         " + ", ".join(f"`{d}`" for d in a.dependencies[:4]))
    console.print(
        "\n  [dim]Nada foi criado. Para aplicar:[/]"
        f'\n    [bold]ragx task plan "{safe_echo(request, 46)}" --apply[/]\n'
    )


@app.command("plan")
def plan_cmd(
    request: Annotated[str, typer.Argument()],
    apply: Annotated[bool, typer.Option("--apply", help="Cria projeto, documentos e tarefas.")] = False,
    docs: Annotated[bool, typer.Option("--docs/--no-docs", help="Gravar os esqueletos.")] = True,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Monta o plano: documentos, tarefas e dependências."""
    from ragx.tasks import service

    cfg = load_config()
    p = service.plan_work(cfg, request, apply=apply, write_docs=docs)
    if as_json:
        console.print_json(json.dumps(p.to_dict(), ensure_ascii=False))
        return

    a = p.analysis
    console.print(f'\n[bold]Plano[/] — "{safe_echo(request, 66)}"')
    console.print(f"  {a.classification.value} · {a.strategy}\n")

    if not p.tasks:
        console.print(
            "  [green]Execução direta.[/] Este pedido não justifica projeto —"
            "\n  [dim]criar board para isto seria burocracia sem retorno.[/]\n"
        )
        return

    if p.documents:
        console.print(f"  [bold]Documentos[/] ({len(p.documents)})")
        for d in p.documents:
            marca = f"  [yellow]{len(d['gaps'])} pendência(s)[/]" if d["gaps"] else ""
            console.print(f"    [cyan]{d['doc_type']:<14}[/] {d['rel_path']}{marca}")
        console.print()

    console.print(f"  [bold]Tarefas[/] ({len(p.tasks)}, {p.dependencies} dependências)")
    for t in p.tasks:
        apr = " [magenta](aprovação)[/]" if t["requires_approval"] else ""
        console.print(
            f"    [dim]{t['id'].rsplit('-', 1)[-1]}[/] {t['title']:<32} "
            f"[dim]{t['track']}[/]{apr}"
        )
    if p.skipped_tracks:
        console.print(f"\n  [dim]trilhas não aplicáveis: {', '.join(p.skipped_tracks)}[/]")

    if p.applied:
        console.print(f"\n  [green]✓[/] projeto [bold]{p.project_id}[/] criado")
        for f in p.written_files:
            console.print(f"    [green]+[/] {f}")
        console.print("\n  [dim]Próximo:[/] [bold]ragx task next[/]\n")
    else:
        console.print(
            "\n  [dim]Nada foi criado. Repita com[/] [bold]--apply[/] [dim]para criar.[/]\n"
        )


@app.command("list")
def list_cmd(
    project: Annotated[str | None, typer.Option("--project")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lista as tarefas."""
    from ragx.tasks.store import TaskRepository

    with _conn() as conn:
        tarefas = TaskRepository(conn).list_tasks(project_id=project, status=status)
    if as_json:
        console.print_json(json.dumps(tarefas, ensure_ascii=False, default=str))
        return
    if not tarefas:
        console.print("\n[dim]nenhuma tarefa.[/] [bold]ragx task plan \"...\" --apply[/]\n")
        return
    t = Table(box=None, pad_edge=False)
    for col in ("id", "estado", "prio", "trilha", "título"):
        t.add_column(col, style="bold" if col == "título" else None)
    for row in tarefas:
        cor = _CORES.get(row["status"], "white")
        t.add_row(
            row["id"].rsplit("-", 1)[-1], f"[{cor}]{row['status']}[/]",
            row["priority"], row["track"], row["title"],
        )
    console.print()
    console.print(t)
    console.print()


@app.command("show")
def show_cmd(
    task_id: Annotated[str, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Detalhe de uma tarefa."""
    from ragx.tasks.store import TaskRepository

    with _conn() as conn:
        repo = TaskRepository(conn)
        tarefa = repo.get(task_id)
        if tarefa is None:
            raise UsageError(f"tarefa não encontrada: {safe_echo(task_id, 40)}")
        deps = repo.dependencies_of(task_id)
        dependentes = repo.dependents_of(task_id)
        resultado = repo.latest_result(task_id)
    if as_json:
        console.print_json(json.dumps(
            {"task": tarefa, "dependencies": deps, "dependents": dependentes,
             "result": resultado}, ensure_ascii=False, default=str))
        return

    cor = _CORES.get(tarefa["status"], "white")
    console.print(f"\n[bold]{tarefa['id']}[/] — {tarefa['title']}")
    console.print(
        f"  [{cor}]{tarefa['status']}[/] · {tarefa['priority']} · {tarefa['track']}"
        + (" · [magenta]exige aprovação[/]" if tarefa["requires_approval"] else "")
    )
    if tarefa.get("description"):
        console.print(f"\n{tarefa['description']}")
    for rotulo, chave in (
        ("Critérios de aceite", "acceptance_criteria"),
        ("Escopo de arquivos", "files_scope"),
        ("Testes exigidos", "test_requirements"),
        ("Segurança", "security_requirements"),
    ):
        if tarefa.get(chave):
            console.print(f"\n  [bold]{rotulo}[/]")
            for x in tarefa[chave]:
                console.print(f"    - {x}")
    if deps:
        console.print("\n  [bold]Depende de[/]")
        for d in deps:
            c = _CORES.get(d["status"], "white")
            console.print(f"    [{c}]{d['status']:<10}[/] {d['id'].rsplit('-',1)[-1]} {d['title']}")
    if dependentes:
        console.print(f"\n  [bold]Libera[/] {', '.join(x.rsplit('-',1)[-1] for x in dependentes)}")
    if tarefa.get("last_error"):
        console.print(f"\n  [red]último erro:[/] {tarefa['last_error'][:200]}")
    console.print()


@app.command("next")
def next_cmd(
    project: Annotated[str | None, typer.Option("--project")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """A próxima tarefa executável. Não reivindica."""
    from ragx.tasks.dispatcher import TaskDispatcher
    from ragx.tasks.store import TaskRepository

    cfg, ctx = _repo(read_only=True)
    with ctx as conn:
        tarefa = TaskDispatcher(cfg, TaskRepository(conn)).next(project)
    if as_json:
        console.print_json(json.dumps(tarefa or {}, ensure_ascii=False, default=str))
        return
    if tarefa is None:
        console.print("\n[dim]nenhuma tarefa pronta.[/]\n")
        return
    console.print(f"\n[bold]{tarefa['id']}[/] — {tarefa['title']}")
    console.print(f"  [dim]{tarefa['track']} · {tarefa['priority']}[/]")
    console.print(f"\n  [dim]Para o contexto:[/] [bold]ragx task context {tarefa['id']}[/]\n")


@app.command("context")
def context_cmd(
    task_id: Annotated[str, typer.Argument()],
    tokens: Annotated[int, typer.Option("--tokens")] = 0,
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Imprime o contexto que o agente receberia para esta tarefa."""
    from ragx.tasks.dispatcher import build_task_context
    from ragx.tasks.store import TaskRepository

    cfg, ctx = _repo(read_only=True)
    with ctx as conn:
        repo = TaskRepository(conn)
        tarefa = repo.get(task_id)
        if tarefa is None:
            raise UsageError(f"tarefa não encontrada: {safe_echo(task_id, 40)}")
        corpo, n, fontes, _deps, _dec = build_task_context(
            cfg, repo, tarefa, tokens or cfg.tasks.context_tokens
        )
    if out:
        out.write_text(corpo, encoding="utf-8", newline="\n")
        console.print(f"\n[green]✓[/] {out}  [dim]{n} tokens, {len(fontes)} fontes[/]\n")
        return
    console.print(corpo)


@app.command("run")
def run_cmd(
    task_id: Annotated[str | None, typer.Argument()] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
) -> None:
    """Reivindica a tarefa e imprime o pacote para o agente executar.

    O RAGX entrega o trabalho; quem executa é o agente (ADR-0015).
    """
    from ragx.tasks.dispatcher import TaskDispatcher
    from ragx.tasks.store import TaskRepository, open_tasks_db

    cfg = load_config()
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        d = TaskDispatcher(cfg, repo, worker=cfg.tasks.worker_id or "cli").claim(
            task_id, project
        )
        conn.commit() if conn.in_transaction else None
    if d is None:
        console.print("\n[dim]nenhuma tarefa disponível para reivindicar.[/]\n")
        raise typer.Exit(1)
    console.print(d.context)
    console.print(
        f"\n---\n[dim]Ao terminar:[/] "
        f"[bold]ragx task result {d.task['id']} --file resultado.json[/]\n"
    )


@app.command("result")
def result_cmd(
    task_id: Annotated[str, typer.Argument()],
    file: Annotated[Path | None, typer.Option("--file", help="JSON do resultado.")] = None,
    summary: Annotated[str | None, typer.Option("--summary")] = None,
    status: Annotated[str, typer.Option("--status")] = "completed",
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Entrega o resultado da tarefa; dispara validação e liberação."""
    from ragx.tasks.dispatcher import TaskDispatcher, result_from_json
    from ragx.tasks.store import TaskRepository, open_tasks_db

    cfg = load_config()
    if file:
        payload = result_from_json(file.read_text(encoding="utf-8"))
    elif summary:
        payload = {"status": status, "summary": summary}
    else:
        raise UsageError("informe --file ou --summary")

    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        disp = TaskDispatcher(cfg, repo, worker=cfg.tasks.worker_id or "cli")
        v, estado = disp.report(task_id, payload)
        conn.commit() if conn.in_transaction else None

    if as_json:
        console.print_json(json.dumps(
            {"valid": v.ok, "failures": v.failures, "warnings": v.warnings,
             "state": estado}, ensure_ascii=False))
        return
    if v.ok:
        console.print(f"\n[green]✓[/] {task_id} — {estado['status']}")
        if estado.get("unblocked"):
            console.print(
                "  liberou: " + ", ".join(x.rsplit("-", 1)[-1] for x in estado["unblocked"])
            )
    else:
        console.print(f"\n[red]✗[/] {task_id} — resultado recusado")
        for f in v.failures:
            console.print(f"    [red]•[/] {f}")
        console.print(f"  [dim]estado: {estado['status']}[/]")
    for w in v.warnings:
        console.print(f"    [yellow]![/] {w}")
    console.print()


@app.command("validate")
def validate_cmd(
    task_id: Annotated[str, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Revalida o último resultado sem mudar estado."""
    from ragx.tasks.dispatcher import validate
    from ragx.tasks.models import TaskResult
    from ragx.tasks.store import TaskRepository

    cfg, ctx = _repo(read_only=True)
    with ctx as conn:
        repo = TaskRepository(conn)
        tarefa = repo.get(task_id)
        if tarefa is None:
            raise UsageError(f"tarefa não encontrada: {safe_echo(task_id, 40)}")
        r = repo.latest_result(task_id)
    if r is None:
        console.print(f"\n[dim]{task_id} ainda não tem resultado.[/]\n")
        raise typer.Exit(1)
    v = validate(cfg, tarefa, TaskResult.from_dict(r["payload"]))
    if as_json:
        console.print_json(json.dumps(
            {"valid": v.ok, "failures": v.failures, "warnings": v.warnings},
            ensure_ascii=False))
        return
    console.print(f"\n{'[green]✓ válido[/]' if v.ok else '[red]✗ inválido[/]'}")
    for f in v.failures:
        console.print(f"  [red]•[/] {f}")
    for w in v.warnings:
        console.print(f"  [yellow]![/] {w}")
    console.print()


@app.command("retry")
def retry_cmd(task_id: Annotated[str, typer.Argument()]) -> None:
    """Devolve a tarefa à fila imediatamente."""
    from ragx.tasks.models import Status

    _transition(task_id, Status.READY, "retry manual")


@app.command("cancel")
def cancel_cmd(task_id: Annotated[str, typer.Argument()]) -> None:
    """Cancela a tarefa. Decisão humana; não se desfaz sozinha."""
    from ragx.tasks.models import Status

    _transition(task_id, Status.CANCELLED, "cancelada pelo usuário")


@app.command("block")
def block_cmd(
    task_id: Annotated[str, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Bloqueia a tarefa."""
    from ragx.tasks.models import Status

    _transition(task_id, Status.BLOCKED, reason or "bloqueada pelo usuário")


@app.command("unblock")
def unblock_cmd(task_id: Annotated[str, typer.Argument()]) -> None:
    """Desbloqueia; volta a `pending` e o worker decide se já está pronta."""
    from ragx.tasks.models import Status

    _transition(task_id, Status.PENDING, "desbloqueada")


def _transition(task_id: str, novo: Status, detalhe: str) -> None:
    from ragx.tasks.store import TaskRepository, open_tasks_db

    cfg = load_config()
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        if repo.get(task_id) is None:
            raise UsageError(f"tarefa não encontrada: {safe_echo(task_id, 40)}")
        repo.set_status(task_id, novo, actor="cli", detail=detalhe)
        conn.commit() if conn.in_transaction else None
    console.print(f"\n[green]✓[/] {task_id} → [bold]{novo}[/]\n")


@app.command("dependencies")
def dependencies_cmd(
    task_id: Annotated[str, typer.Argument()],
    add: Annotated[str | None, typer.Option("--add", help="Tarefa da qual esta passa a depender.")] = None,
    kind: Annotated[str, typer.Option("--kind")] = "depends_on",
) -> None:
    """Mostra ou cria dependências."""
    from ragx.tasks.models import DependencyKind
    from ragx.tasks.store import TaskRepository, open_tasks_db

    cfg = load_config()
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        if add:
            repo.add_dependency(task_id, add, DependencyKind(kind))
            conn.commit() if conn.in_transaction else None
            console.print(f"\n[green]✓[/] {task_id} {kind} {add}\n")
            return
        deps = repo.dependencies_of(task_id)
        dependentes = repo.dependents_of(task_id)
    console.print(f"\n[bold]{task_id}[/]")
    console.print("  depende de: " + (", ".join(d["id"] for d in deps) or "[dim]nada[/]"))
    console.print("  libera:     " + (", ".join(dependentes) or "[dim]nada[/]"))
    console.print()


@app.command("graph")
def graph_cmd(
    project: Annotated[str | None, typer.Option("--project")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Desenha o DAG do projeto."""
    from ragx.tasks.store import TaskRepository

    with _conn() as conn:
        repo = TaskRepository(conn)
        tarefas = repo.list_tasks(project_id=project, limit=500)
        arestas = repo.edges(project)
    if as_json:
        console.print_json(json.dumps(
            {"nodes": [{"id": t["id"], "title": t["title"], "status": t["status"]}
                       for t in tarefas],
             "edges": [{"from": a, "to": b, "kind": k} for a, b, k in arestas]},
            ensure_ascii=False))
        return
    if not tarefas:
        console.print("\n[dim]nenhuma tarefa.[/]\n")
        return

    entrada: dict[str, list[str]] = {t["id"]: [] for t in tarefas}
    for origem, destino, _k in arestas:
        entrada.setdefault(origem, []).append(destino)

    console.print()
    for t in tarefas:
        cor = _CORES.get(t["status"], "white")
        curto = t["id"].rsplit("-", 1)[-1]
        deps = [d.rsplit("-", 1)[-1] for d in entrada.get(t["id"], [])]
        seta = f"  [dim]← {', '.join(deps)}[/]" if deps else ""
        console.print(f"  [{cor}]●[/] [bold]{curto}[/] {t['title']:<34}{seta}")
    console.print()


@app.command("status")
def status_cmd(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Painel: tarefas, projetos, conhecimento e agendamento."""
    from ragx.tasks import service

    cfg = load_config()
    panel = service.status_panel(cfg)
    if as_json:
        console.print_json(json.dumps(panel, ensure_ascii=False, default=str))
        return

    console.print("\n[bold]RAGX — orquestração[/]\n")
    console.print("  [bold]Tarefas[/]")
    contagens = panel.get("tasks") or {}
    if not contagens:
        console.print("    [dim]nenhuma[/]")
    for estado in ("pending", "ready", "queued", "running", "blocked",
                   "waiting_approval", "retrying", "failed", "completed"):
        n = contagens.get(estado, 0)
        if n:
            console.print(f"    [{_CORES.get(estado,'white')}]{estado:<18}[/] {n}")

    if panel.get("projects"):
        console.print("\n  [bold]Projetos[/]")
        for p in panel["projects"][:10]:
            console.print(f"    {p['status']:<10} {p['name']}")

    k = panel.get("knowledge") or {}
    if k:
        console.print("\n  [bold]Conhecimento[/]")
        for rotulo, chave in (("Documentos", "documents"), ("Chunks", "chunks"),
                              ("Entidades", "entities"), ("Relações", "relations")):
            console.print(f"    {rotulo:<12} {k.get(chave, 0):>8,}")

    s = panel.get("scheduler") or {}
    console.print("\n  [bold]Scheduler[/]")
    console.print(f"    {s.get('enabled', 0)} de {s.get('total', 0)} ativos")
    if s.get("next"):
        console.print(f"    próxima execução: {s['next']}")
    console.print()


@app.command("logs")
def logs_cmd(
    task_id: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option("--limit")] = 50,
    events: Annotated[bool, typer.Option("--events", help="Mostrar eventos em vez de logs.")] = False,
) -> None:
    """Logs ou trilha de eventos da tarefa."""
    from ragx.tasks.store import TaskRepository

    with _conn() as conn:
        repo = TaskRepository(conn)
        linhas: list[dict[str, Any]] = (
            repo.events(task_id, limit) if events else repo.logs(task_id, limit)
        )
    console.print()
    if not linhas:
        console.print("  [dim]nada registrado.[/]\n")
        return
    for ln in reversed(linhas):
        if events:
            console.print(
                f"  [dim]{ln['created_at']}[/] [cyan]{ln['type']}[/] "
                f"{ln.get('from_state') or ''}→{ln.get('to_state') or ''} "
                f"[dim]{ln.get('detail','')}[/]"
            )
        else:
            console.print(f"  [dim]{ln['created_at']}[/] {ln['level']:<6} {ln['message']}")
    console.print()

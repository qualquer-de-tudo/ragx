"""CLI do RAGX. Binário `ragx` (alias histórico `rag`) — ver ADR-0007."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from ragx.cli.commands import (
    agent_cmd,
    base_cmd,
    claude_cmd,
    config_cmd,
    context_cmd,
    dictionary_cmd,
    doctor,
    eval_cmd,
    federation_cmd,
    graph_cmd,
    hooks_cmd,
    index_cmd,
    init,
    maintenance_cmd,
    mcp_cmd,
    perf_cmd,
    portability_cmd,
    search_cmd,
    security,
    size,
    sync_cmd,
    task_cmd,
    trial_cmd,
    watch_cmd,
    worker_cmd,
)
from ragx.core.errors import RagxError

app = typer.Typer(
    name="ragx",
    help="RAGX — Knowledge Engine local: indexa, protege segredos, busca e serve agentes.",
    add_completion=False,
    rich_markup_mode="rich",
)

app.command("init")(init.init)
app.command("doctor")(doctor.doctor)
app.command("index")(index_cmd.index)
app.command("status")(index_cmd.status)
app.command("runs")(index_cmd.runs)
app.command("search")(search_cmd.search)
app.command("context")(context_cmd.context)
app.command("trial")(trial_cmd.trial_cmd)
app.command("perf")(perf_cmd.perf)
app.command("eval")(eval_cmd.eval_cmd)
app.command("trial")(trial_cmd.trial_cmd)
app.command("entities")(graph_cmd.entities)
app.command("graph-search")(graph_cmd.graph_search)
app.command("documents")(index_cmd.documents)
app.command("chunks")(index_cmd.chunks)
app.command("chunk")(index_cmd.chunk)
app.command("size")(size.size)
app.command("vacuum")(maintenance_cmd.vacuum)
app.command("reset")(maintenance_cmd.reset)
app.command("sync")(sync_cmd.sync)
app.command("watch")(watch_cmd.watch)
app.command("worker")(worker_cmd.worker)
app.command("export")(portability_cmd.export)
app.command("import")(portability_cmd.import_)
app.command("inspect")(portability_cmd.inspect)
app.command("contract")(federation_cmd.contract)
app.command(
    "hook-run",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(hooks_cmd.hook_run)
app.add_typer(agent_cmd.app, name="agent", help="Perfis de agente.")
app.add_typer(base_cmd.app, name="base", help="Conhecimento base compartilhado entre projetos.")
app.add_typer(task_cmd.app, name="task", help="Análise, planejamento e execução de trabalho.")
app.add_typer(worker_cmd.app, name="schedule", help="Agendamentos de disparo.")
app.add_typer(dictionary_cmd.app, name="dictionary", help="Knowledge Dictionary.")
app.add_typer(graph_cmd.app, name="graph", help="Grafo de conhecimento.")
app.add_typer(federation_cmd.federation_app, name="federation", help="Superfície pública do projeto.")
app.add_typer(federation_cmd.project_app, name="project", help="Projetos registrados no hub.")
app.add_typer(federation_cmd.hub_app, name="hub", help="Hub multiprojeto local.")
app.add_typer(mcp_cmd.app, name="mcp", help="Servidor MCP.")
app.add_typer(claude_cmd.app, name="claude", help="Liga e desliga o RAGX no Claude Code (global).")
app.add_typer(hooks_cmd.app, name="hooks", help="Hooks de git que mantêm o índice na branch atual.")
app.add_typer(security.app, name="security", help="Varredura e regras de segurança.")
app.add_typer(config_cmd.app, name="config", help="Inspeção e ajuste de configuração.")


def _version_text() -> str:
    from importlib.metadata import version as _v

    return f"ragx {_v('ragx')}"


@app.command("version")
def version() -> None:
    """Imprime a versão instalada."""
    Console().print(_version_text())


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    show_version: bool = typer.Option(
        False, "--version", help="Imprime a versão e sai.", is_eager=True
    ),
) -> None:
    """`ragx --version` além de `ragx version`: a documentação prometia a flag,
    e documentação é contrato.

    `invoke_without_command` é o que permite a flag sozinha chegar até aqui; em
    troca, `ragx` sem argumento passa a cair neste callback, e a ajuda precisa
    ser impressa à mão.
    """
    if show_version:
        Console().print(_version_text())
        raise typer.Exit
    if ctx.invoked_subcommand is None:
        Console().print(ctx.get_help())
        raise typer.Exit


def _invocar() -> None:
    """Executa a CLI SEM deixar o Click reescrever os argumentos.

    No Windows o Click expande curinga contra o diretório atual antes de
    entregar os argumentos ao comando (`windows_expand_args=True`, o padrão).
    Para uma ferramenta cujos argumentos são PADRÕES e CONSULTAS, isso é
    corrupção silenciosa: `ragx documents --path "*src*"` chegava como
    `--path src` porque existe uma pasta `src` ali, e a listagem voltava vazia.
    O mesmo valor daria resultados diferentes em duas pastas diferentes.

    Medido neste repo: `--path "*ragx*"` virava `ragx.toml` — um arquivo — e
    a busca devolvia exatamente um documento.
    """
    typer.main.get_command(app)(windows_expand_args=False)


def main() -> None:
    err = Console(stderr=True)
    try:
        _invocar()
    except RagxError as exc:
        err.print(f"[bold red]erro:[/] {exc}")
        raise SystemExit(exc.exit_code) from exc
    except KeyboardInterrupt:
        err.print("[yellow]interrompido[/]")
        raise SystemExit(130) from None


if __name__ == "__main__":
    sys.exit(main())

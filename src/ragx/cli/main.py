"""CLI do RAGX. Binário `ragx` (alias histórico `rag`) — ver ADR-0007."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from ragx.cli.commands import (
    ab_cmd,
    agent_cmd,
    base_cmd,
    bench_cmd,
    claude_cmd,
    config_cmd,
    context_cmd,
    dictionary_cmd,
    doctor,
    eval_cmd,
    federation_cmd,
    gold_cmd,
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
    touch_cmd,
    trial_cmd,
    watch_cmd,
    worker_cmd,
    worktree_cmd,
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
app.command("ab")(ab_cmd.ab)
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
app.command("touch")(touch_cmd.touch)
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
app.add_typer(bench_cmd.app, name="bench", help="Benchmark local de modelos de embedding e reranker.")
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
app.add_typer(gold_cmd.app, name="gold", help="Conjunto-ouro de avaliação derivado do git.")
app.add_typer(hooks_cmd.app, name="hooks", help="Hooks de git que mantêm o índice na branch atual.")
app.add_typer(worktree_cmd.app, name="worktree", help="Worktrees do repositório e o cache de embedding que compartilham.")
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


#: Comandos de CONSULTA que entram no log de atividade (`.ragx/logs/cli.jsonl`).
#: Manutenção (`index`, `sync`...) já fica no histórico de indexações.
_COMANDOS_REGISTRADOS = frozenset({"search", "context", "graph-search", "chunk", "trial"})


def _comando(argv: list[str]) -> str | None:
    return next((a for a in argv if not a.startswith("-")), None)


def _registrar(inicio: float, codigo: int) -> None:
    """Deixa a tela de atividade do painel ver uma consulta feita no terminal.

    Grava o nome do comando, o tempo e se deu certo; nunca a consulta nem os
    argumentos. O próprio painel roda a CLI o tempo todo (`status`, `trial`),
    e marca isso com `RAGX_CALLER=painel`: essas não entram.
    """
    import os
    import time

    comando = _comando(sys.argv[1:])
    if comando not in _COMANDOS_REGISTRADOS or os.environ.get("RAGX_CALLER") == "painel":
        return
    try:
        from ragx.config import load_config
        from ragx.diagnostics import log_cli_call
        from ragx.storage.db import utcnow

        cfg = load_config()
        if not cfg.db_path.exists():
            return
        log_cli_call(cfg.state_dir, {
            "ts": utcnow(),
            "command": comando,
            "ms": round((time.monotonic() - inicio) * 1000, 1),
            "ok": codigo == 0,
            "project": cfg.project.name or cfg.root.name,
        }, cfg.log.retain_days)
    except Exception:
        pass


def main() -> None:
    import time

    err = Console(stderr=True)
    inicio = time.monotonic()
    codigo = 1
    try:
        _invocar()
        codigo = 0
    except SystemExit as exc:
        codigo = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        raise
    except RagxError as exc:
        codigo = exc.exit_code
        err.print(f"[bold red]erro:[/] {exc}")
        raise SystemExit(exc.exit_code) from exc
    except KeyboardInterrupt:
        codigo = 130
        err.print("[yellow]interrompido[/]")
        raise SystemExit(130) from None
    finally:
        _registrar(inicio, codigo)


if __name__ == "__main__":
    sys.exit(main())

"""`ragx trial` — a economia estimada de contexto, com a ressalva junto."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()

_SCOPES = ("sources", "project")


def trial(
    query: Annotated[str, typer.Argument(help="A pergunta que o contexto deve responder.")],
    tokens: Annotated[int, typer.Option("--tokens", help="Orçamento do contexto.")] = 3000,
    scope: Annotated[
        str,
        typer.Option(
            "--scope",
            help="Basal: `sources` (os arquivos que o contexto usou) ou `project` (tudo).",
        ),
    ] = "sources",
    path: Annotated[
        list[str] | None,
        typer.Option("--path", help="Basal explícito por glob (repetível)."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compara o contexto montado com a leitura integral dos arquivos.

    O resultado é uma ESTIMATIVA de ordem de grandeza — não uma previsão do que
    um modelo vai cobrar. Ver `ragx trial --help` e docs/07-context-engine.md.
    """
    from ragx import trial as motor

    if scope not in _SCOPES:
        raise UsageError(f"escopo inválido: {scope!r} (use {' | '.join(_SCOPES)})")
    if tokens < 200:
        raise UsageError(f"--tokens mínimo é 200 (recebido: {tokens})")

    cfg = load_config()
    # Os globs são filtrados contra o que o walker emite, e não expandidos
    # contra o disco: assim `--path "*"` não passa a alcançar o `.env`, e
    # `--path "../../etc/*"` não sai da raiz do projeto.
    r = motor.run(cfg, query, tokens=tokens, scope=scope, globs=list(path) if path else None)
    if path and r.baseline.files == 0 and not r.baseline.excluded:
        raise UsageError(f"nenhum arquivo indexável casou com {path!r} em {cfg.root}")

    if as_json:
        console.print_json(json.dumps(r.to_dict(), ensure_ascii=False))
        return

    b = r.baseline
    console.print(f'\n[bold]Contexto para[/] "{r.query}"\n')
    console.print(
        f"  contexto montado   [green]{r.context_tokens:>9,}[/] tokens  "
        f"[dim]({r.context_fragments} trecho(s) de {r.context_sources} arquivo(s), "
        f"orçamento {r.budget:,})[/]"
    )
    console.print(
        f"  leitura integral   [yellow]{b.tokens:>9,}[/] tokens  "
        f"[dim]({b.files} arquivo(s), {b.bytes_read:,} bytes)[/]"
    )

    if r.saved_ratio is None:
        # Sem basal não há razão; imprimir "0%" afirmaria o que não se sabe.
        console.print(
            "\n  [yellow]sem basal para comparar[/] — nenhum arquivo legível no escopo "
            f"[dim]({scope})[/]\n"
        )
    else:
        sinal = "menos" if r.saved_tokens >= 0 else "[red]A MAIS[/]"
        console.print(
            f"\n  diferença          [bold]{abs(r.saved_tokens):>9,}[/] tokens {sinal}  "
            f"[bold]({r.saved_ratio:.1%})[/]\n"
        )

    if b.empty_files:
        console.print(f"  [dim]{b.empty_files} arquivo(s) vazio(s) — lidos, 0 tokens[/]")
    if b.excluded:
        console.print("  [dim]fora do basal:[/]")
        for motivo, n in sorted(b.excluded.items()):
            console.print(f"    [dim]{n:>5} × {motivo}[/]")
        console.print(
            "    [dim]exclusão SUBESTIMA a economia — é o lado seguro do erro[/]"
        )

    # A ressalva é impressa por último, que é onde o olho para.
    console.print(f"\n  [yellow]![/] [dim]{motor.RESSALVA}[/]")
    console.print(f"  [dim]contador de tokens: {r.counter}[/]\n")

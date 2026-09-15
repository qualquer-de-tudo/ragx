"""`ragx size` — orçamento de tamanho (docs/16-orcamento-de-tamanho.md)."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.sizing.budget import Budget

console = Console()


def size(
    check: Annotated[bool, typer.Option("--check", help="Exit 1 se estourar (CI).")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Relatório do orçamento de `knowledge/`."""
    cfg = load_config()
    b = Budget(cfg)
    report = b.report()

    if as_json:
        console.print_json(json.dumps(report, ensure_ascii=False))
    else:
        console.print(f"\n[bold]Conhecimento versionado[/] — {cfg.knowledge_dir.name}/\n")
        if not report["categories"]:
            console.print("  [dim]nada gravado ainda[/]\n")
        for name, info in report["categories"].items():
            console.print(f"    {name:<18} {info['files']:>6} arquivos   {_mb(info['bytes'])}")
        pct = report["pct_of_warn"]
        bar = "█" * min(int(pct / 10), 10) + "░" * max(0, 10 - int(pct / 10))
        console.print(
            f"\n    {'total':<18} {report['files']:>6} arquivos   "
            f"{_mb(report['bytes'])}   {bar}  {pct:.0f}% de {_mb(report['warn_limit'])}"
        )
        if report["largest"]:
            lg = report["largest"]
            console.print(
                f"\n    maior artefato     {lg['path']}   {_mb(lg['bytes'])}"
                f"   (limite {_mb(report['artifact_limit'])})"
            )
        console.print()
        for w in report["warnings"]:
            console.print(f"  [yellow]! {w}[/]")
        if report["exceeded"]:
            console.print(f"  [bold red]✗ excede fail_total_bytes ({_mb(report['fail_limit'])})[/]")
            for s in report["suggestions"]:
                console.print(f"    [yellow]→ {s}[/]")
        console.print()

    if check and (report["exceeded"] or report["oversized"]):
        raise typer.Exit(1)


def _mb(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"

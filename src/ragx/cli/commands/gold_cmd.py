"""`ragx gold build` — conjunto-ouro derivado do git (RAGX-0167)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command("build")
def build(
    limit: Annotated[int | None, typer.Option("--limit", help="só os N commits mais recentes")] = None,
    max_files: Annotated[int, typer.Option("--max-files", help="descarta commit com mais arquivos relevantes que isto")] = 8,
    out: Annotated[Path, typer.Option("--out")] = Path("tests/eval/gold-git.yaml"),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="só o funil, sem escrever")] = False,
) -> None:
    """Gera o conjunto-ouro a partir do git: a mensagem do commit é a consulta e os arquivos alterados, o gabarito."""
    from ragx import gitinfo
    from ragx.search.gold import derive_cases, render_yaml
    from ragx.storage.db import open_db

    cfg = load_config()
    if not cfg.db_path.exists():
        raise UsageError("sem índice: rode `ragx index .` antes")
    commits = gitinfo.log_commits(cfg.root, limit=limit)
    if commits is None:
        raise UsageError("não consegui ler o histórico do git (fora de um repositório, ou git ausente)")
    with open_db(cfg.db_path, read_only=True) as conn:
        indexed = {r["rel_path"]: r["doc_kind"] for r in conn.execute("SELECT rel_path, doc_kind FROM documents")}
    resultado = derive_cases(commits, indexed, max_files=max_files)

    console.print("\n[bold]Funil do conjunto-ouro[/]\n")
    for linha in resultado.funnel.linhas():
        console.print(f"  {linha}")
    if dry_run:
        console.print("\n  [dim]--dry-run: nada foi escrito.[/]\n")
        return
    head = (gitinfo.git(cfg.root, "rev-parse", "--short", "HEAD") or "desconhecido").strip()
    alvo = out if out.is_absolute() else cfg.root / out
    alvo.parent.mkdir(parents=True, exist_ok=True)
    texto = render_yaml(resultado, head)
    alvo.write_text(texto, encoding="utf-8", newline="\n")
    console.print(f"\n  {len(resultado.cases)} consultas em [bold]{alvo}[/]  [dim](avalie com: ragx eval --queries {out})[/]\n")

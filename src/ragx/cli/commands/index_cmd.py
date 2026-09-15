"""`ragx index`, `ragx status`, `ragx documents`, `ragx chunks`, `ragx chunk`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from ragx.config import load_config
from ragx.core.errors import UsageError
from ragx.indexing.pipeline import index_project
from ragx.indexing.pipeline import status as get_status
from ragx.storage.db import open_db
from ragx.storage.repositories import ChunkRepo, DocumentRepo

console = Console()


def index(
    path: Annotated[Path, typer.Argument()] = Path("."),
    full: Annotated[bool, typer.Option("--full", help="Ignora cache; reindexa tudo.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Relatório sem escrever.")] = False,
    exclude: Annotated[list[str] | None, typer.Option("--exclude")] = None,
    include: Annotated[list[str] | None, typer.Option("--include")] = None,
    embed_only: Annotated[bool, typer.Option("--embed-only", help="Só gera vetores faltantes.")] = False,
    no_embed: Annotated[bool, typer.Option("--no-embed", help="Não gera vetores.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
    quiet: Annotated[bool, typer.Option("--quiet")] = False,
) -> None:
    """Indexa o projeto (incremental por padrão)."""
    cfg = load_config(path)
    if exclude:
        cfg.index.exclude = [*cfg.index.exclude, *exclude]
    if include:
        cfg.index.include = [*cfg.index.include, *include]

    mode = "completa" if full else "incremental"
    if not quiet and not as_json:
        console.print(f"\n[bold]Indexando[/] {cfg.root}  ([cyan]{mode}[/])\n")

    if quiet or as_json:
        report = index_project(
            cfg, full=full, dry_run=dry_run, embed=not no_embed, embed_only=embed_only
        )
    else:
        with Progress(
            TextColumn("  [progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("{task.completed} arquivos"),
            console=console,
            transient=True,
        ) as bar:
            task = bar.add_task("varrendo", total=None)

            def tick(n: int, rel: str) -> None:
                bar.update(task, completed=n, description=rel[-46:])

            report = index_project(
                cfg, full=full, dry_run=dry_run, progress=tick,
                embed=not no_embed, embed_only=embed_only,
            )

    s = report.stats
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "root": str(cfg.root), "mode": mode, "dry_run": dry_run,
                    "files_seen": s.files_seen, "documents_indexed": s.indexed,
                    "unchanged": s.unchanged, "new_documents": report.new_documents,
                    "modified_documents": report.modified_documents,
                    "chunks": report.new_chunks, "skipped": s.skipped,
                    "skip_reasons": s.skip_reasons, "blocked": s.blocked,
                    "redacted": s.redacted, "removed": s.removed,
                    "degraded": report.degraded, "duration_ms": s.duration_ms,
                    "embedded": s.embedded, "embed_error": report.embed_error,
                },
                ensure_ascii=False,
            )
        )
        return
    if quiet:
        return

    st = get_status(cfg)
    console.print(
        f"  Documents  {st.get('documents', 0):>8,}   "
        f"[green]+{report.new_documents} novos[/], {report.modified_documents} modificados, "
        f"{s.removed} removidos"
    )
    console.print(f"  Chunks     {st.get('chunks', 0):>8,}   [green]+{report.new_chunks}[/]")
    console.print(f"  Unchanged  {s.unchanged:>8,}")
    if st.get("embeddings"):
        console.print(f"  Embeddings {st['embeddings']:>8,}   [green]+{s.embedded}[/]")
    if s.skipped:
        detail = ", ".join(f"{v} {k}" for k, v in sorted(s.skip_reasons.items(), key=lambda kv: -kv[1])[:4])
        console.print(f"  Skipped    {s.skipped:>8,}   [dim]{detail}[/]")
    if s.blocked:
        console.print(
            f"  [red]Blocked    {s.blocked:>8,}[/]   [dim]ragx security scan . para detalhes[/]"
        )
    if s.redacted:
        console.print(f"  [yellow]Redacted   {s.redacted:>8,}[/]")
    if report.degraded:
        console.print(f"  [yellow]Degraded   {report.degraded:>8,}[/]   [dim]parsing caiu no fallback[/]")
    console.print(f"\n  Tempo {s.duration_ms / 1000:.1f} s" + ("  [dim](dry-run)[/]" if dry_run else ""))
    console.print()


def status(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Resumo do índice e do último run."""
    cfg = load_config()
    st = get_status(cfg)
    if as_json:
        console.print_json(json.dumps(st, ensure_ascii=False, default=str))
        return
    if not st.get("initialized"):
        console.print("\n[yellow]Projeto não inicializado.[/] Rode: [bold]ragx init[/]\n")
        raise typer.Exit(1)
    console.print(f"\n[bold]Índice[/] — {cfg.root}\n")
    console.print(f"  Documents        {st['documents']:>8,}")
    console.print(f"  Chunks           {st['chunks']:>8,}")
    console.print(f"  Embeddings       {st.get('embeddings', 0):>8,}")
    console.print(f"  Security events  {st['security_events']:>8,}")
    m = st.get("embedding_model")
    if m:
        console.print(
            f"  [dim]modelo: {m['id']} ({m['dim']}d, versionado {m['versioned_dim']}d int8)[/]"
        )
    if st["by_lang"]:
        console.print("\n  [bold]Por linguagem[/]")
        for lang, n in list(st["by_lang"].items())[:10]:
            console.print(f"    {lang or '—':<14} {n:>6,}")
    run = st.get("last_run")
    if run:
        console.print(
            f"\n  [dim]Último run: {run['mode']} em {run['started_at']} "
            f"({run.get('duration_ms', 0) / 1000:.1f}s)[/]"
        )
    console.print()


def documents(
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    kind: Annotated[str | None, typer.Option("--kind")] = None,
    path_glob: Annotated[str | None, typer.Option("--path")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lista documentos indexados."""
    cfg = load_config()
    with open_db(cfg.db_path, read_only=True) as conn:
        rows = DocumentRepo(conn).list(lang=lang, kind=kind, path_like=path_glob, limit=limit)
    if as_json:
        console.print_json(json.dumps(rows, ensure_ascii=False, default=str))
        return
    if not rows:
        console.print("\n[dim]nenhum documento[/]\n")
        return
    console.print()
    for r in rows:
        flag = " [yellow]R[/]" if r["redacted"] else ""
        console.print(
            f"  {r['rel_path']:<52} [cyan]{r['lang'] or '—':<11}[/]"
            f"{r['doc_kind']:<8}{r['size_bytes']:>8,}B{flag}"
        )
    console.print(f"\n  {len(rows)} documento(s)\n")


def chunks(
    document: Annotated[str | None, typer.Option("--document")] = None,
    symbol: Annotated[str | None, typer.Option("--symbol")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lista chunks de um documento."""
    cfg = load_config()
    if not document:
        raise UsageError("informe --document <caminho>")
    with open_db(cfg.db_path, read_only=True) as conn:
        rows = ChunkRepo(conn).for_document(document, limit=limit)
    if symbol:
        rows = [r for r in rows if r["symbol"] and symbol in r["symbol"]]
    if as_json:
        console.print_json(json.dumps(rows, ensure_ascii=False, default=str))
        return
    if not rows:
        console.print(f"\n[dim]nenhum chunk para {document}[/]\n")
        return
    console.print()
    for r in rows:
        label = r["symbol"] or r["heading_path"] or "—"
        console.print(
            f"  [dim]{r['id'][:10]}[/] {r['ordinal']:>3}  "
            f"[cyan]{r['kind']:<9}[/] L{r['start_line']}-{r['end_line']:<6} "
            f"{r['token_count']:>5}t  {label}"
        )
    console.print(f"\n  {len(rows)} chunk(s)\n")


def chunk(
    chunk_id: Annotated[str, typer.Argument()],
    with_context: Annotated[bool, typer.Option("--with-context")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Conteúdo completo de um chunk."""
    cfg = load_config()
    with open_db(cfg.db_path, read_only=True) as conn:
        repo = ChunkRepo(conn)
        row = repo.get(chunk_id)
        if row is None:
            console.print(f"[red]chunk não encontrado:[/] {chunk_id}")
            raise typer.Exit(1)
        neighbors = repo.neighbors(chunk_id) if with_context else []
    if as_json:
        console.print_json(
            json.dumps({"chunk": row, "neighbors": neighbors}, ensure_ascii=False, default=str)
        )
        return
    console.print(
        f"\n[bold]{row['rel_path']}[/]:{row['start_line']}-{row['end_line']}"
        f"  [cyan]{row['symbol'] or row['heading_path'] or ''}[/]\n"
    )
    console.print(row["content"])
    if neighbors:
        console.print("\n[dim]— vizinhos —[/]")
        for n in neighbors:
            if n["id"] != chunk_id:
                console.print(f"  [dim]{n['id'][:10]} {n['ordinal']} {n['symbol'] or ''}[/]")
    console.print()

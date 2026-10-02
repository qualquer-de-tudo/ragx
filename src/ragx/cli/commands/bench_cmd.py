"""`ragx bench models` — benchmark local de modelos de embedding e reranker (RAGX-0169)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.errors import UsageError

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command("models")
def models(
    candidates: Annotated[Path, typer.Option("--candidates")] = Path("tests/eval/models.yaml"),
    only: Annotated[str | None, typer.Option("--only", help="só o candidato com este nome")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="só lista o que está em disco e estima o tempo")] = False,
    out: Annotated[Path | None, typer.Option("--out", help="grava o resultado em JSON")] = None,
    force_slow: Annotated[bool, typer.Option("--force-slow", help="aceita uma estimativa acima de 20 min")] = False,
) -> None:
    """Mede, no corpus deste projeto, os modelos que JÁ estão em disco. Nunca baixa nada nem escreve no índice real."""
    from ragx.search import bench
    from ragx.search.evaluation import load_cases

    cfg = load_config()
    if not cfg.db_path.exists():
        raise UsageError("sem índice: rode `ragx index .` antes")
    caminho = candidates if candidates.is_absolute() else cfg.root / candidates
    todos = bench.load_candidates(caminho)
    if only:
        todos = [c for c in todos if c.name == only]
        if not todos:
            raise UsageError(f"nenhum candidato chamado {only!r} em {caminho}")

    console.print("\n[bold]Candidatos[/]\n")
    estados = {c.name: bench.probe(c, cfg) for c in todos}
    for c in todos:
        status, detalhe = estados[c.name]
        cor = {"disponivel": "green", "ausente": "yellow"}.get(status, "red")
        nota = "  [red]licença não comercial[/]" if c.non_commercial else ""
        extra = f"  [dim]{c.how_to_get}[/]" if status == "ausente" and c.how_to_get else ""
        console.print(f"  {c.name:<30} {c.kind:<10} [{cor}]{status}[/]  [dim]{detalhe}[/]{nota}{extra}")

    disponiveis = [c for c in todos if estados[c.name][0] == "disponivel"]
    if dry_run:
        console.print("\n  [bold]Estimativa do reembed completo[/]  [dim](64 chunks reais por candidato)[/]")
        for c in (c for c in disponiveis if c.kind == "embedding"):
            seg = bench.estimate_seconds(cfg, c)
            console.print(f"    {c.name:<30} {'—' if seg is None else f'{seg:.0f} s'}")
        console.print("\n  [dim]--dry-run: nada foi medido nem escrito.[/]\n")
        return

    estimativas = {c.name: bench.estimate_seconds(cfg, c) for c in disponiveis if c.kind == "embedding"}
    total = sum(v or 0.0 for v in estimativas.values())
    if total > bench.MAX_ESTIMATE_S and not force_slow:
        raise UsageError(f"estimativa de {total / 60:.0f} min, acima de 20 min; use --force-slow se for de propósito")

    padrao = cfg.root / "tests" / "eval"
    conjuntos = {"manual": load_cases(padrao / "queries.yaml")}
    if (padrao / "gold-git.yaml").is_file():
        conjuntos["git"] = load_cases(padrao / "gold-git.yaml")

    resultados = []
    for c in todos:
        status, detalhe = estados[c.name]
        if status != "disponivel":
            resultados.append(bench.BenchResult(c, status, detalhe, license_note="licença não comercial" if c.non_commercial else ""))
            continue
        console.print(f"  medindo [bold]{c.name}[/] ...")
        if c.kind == "embedding":
            resultados.append(bench.run_embedding(cfg, c, conjuntos))
        else:
            resultados.append(bench.run_reranker(cfg, c, conjuntos))

    console.print("\n[bold]Resultado[/]  [dim](recall@5 [IC95%] / MRR no modo hybrid)[/]\n")
    for r in resultados:
        if r.status != "disponivel":
            console.print(f"  {r.candidate.name:<30} [yellow]{r.status}[/]  [dim]{r.detail}[/]")
            continue
        linhas = []
        for conj, modos in r.metrics.items():
            m = modos.get("hybrid") or modos.get("hybrid+rerank")
            if m:
                linhas.append(f"{conj}: {m.recall_at_5:.2f} [{m.ci[0]:.2f}-{m.ci[1]:.2f}] / {m.mrr:.2f}")
        lat = f" query p50 {r.query_p50_ms} ms" if r.query_p50_ms is not None else ""
        lat += f" rerank 30 pares p50 {r.rerank_p50_ms} ms" if r.rerank_p50_ms is not None else ""
        console.print(f"  {r.candidate.name:<30} {'   '.join(linhas)}{lat}  [dim]{r.license_note}[/]")
    if out:
        alvo = out if out.is_absolute() else cfg.root / out
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps(bench.to_jsonable(resultados), ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"\n  JSON em {alvo}")
    console.print()

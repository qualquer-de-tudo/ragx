"""`ragx eval` — mede a qualidade da recuperação, por modo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config

console = Console()


def eval_cmd(
    queries: Annotated[Path, typer.Option("--queries")] = Path("tests/eval/queries.yaml"),
    mode: Annotated[str, typer.Option("--mode", help="all|hybrid|semantic|keyword")] = "all",
    as_json: Annotated[bool, typer.Option("--json")] = False,
    show_failures: Annotated[bool, typer.Option("--failures")] = False,
) -> None:
    """Recall@5, MRR e nDCG@10 por modo de busca."""
    from ragx.search.evaluation import MAX_CI_WIDTH, MODES, evaluate, load_cases

    cfg = load_config()
    path = queries if queries.is_absolute() else cfg.root / queries
    cases = load_cases(path)
    modes = MODES if mode == "all" else (mode,)
    metrics = evaluate(cfg, cases, modes)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "cases": len(cases),
                    "metrics": [
                        {
                            "mode": m.mode,
                            "recall_at_5": round(m.recall_at_5, 4),
                            "recall_ci_low": round(m.recall_ci[0], 4),
                            "recall_ci_high": round(m.recall_ci[1], 4),
                            "conclusive": m.conclusive,
                            "n": m.cases,
                            "mrr": round(m.mrr, 4),
                            "ndcg_at_10": round(m.ndcg_at_10, 4),
                            "failures": [{"query": q, "rank": r} for q, r in m.failures],
                            "by_class": {k: {"hits": h, "n": t, "recall_at_5": round(h / t, 4)} for k, (h, t) in m.by_class.items()},
                            "by_difficulty": {k: {"hits": h, "n": t, "recall_at_5": round(h / t, 4)} for k, (h, t) in m.by_difficulty.items()},
                            "no_answer": {
                                "cases": m.no_answer_cases,
                                "false_positives": m.no_answer_false_positives,
                                "false_positive_rate": None if m.no_answer_fp_rate is None else round(m.no_answer_fp_rate, 4),
                                "threshold": None if m.no_answer_threshold is None else round(m.no_answer_threshold, 4),
                            },
                        }
                        for m in metrics
                    ],
                },
                ensure_ascii=False,
            )
        )
        return

    sem = sum(1 for c in cases if c.no_answer)
    console.print(f"\n[bold]Avaliação[/] — {len(cases)} consultas ({len(cases) - sem} com resposta, {sem} sem)\n")
    console.print(f"  {'Modo':<12}{'Recall@5':>10}{'IC 95%':>16}{'MRR':>9}{'nDCG@10':>10}")
    console.print(f"  {'-' * 57}")
    for m in metrics:
        ic = f"[{m.recall_ci[0]:.2f}–{m.recall_ci[1]:.2f}]"
        console.print(
            f"  {m.mode:<12}{m.recall_at_5:>10.2f}{ic:>16}"
            f"{m.mrr:>9.2f}{m.ndcg_at_10:>10.2f}"
        )

    # O aviso vem ANTES do veredito. Sem ele, o ✓/✗ é lido como conclusão — foi
    # assim que "0,62 contra 0,77" virou a afirmação publicada de que a busca
    # híbrida falhou o critério, com os intervalos sobrepostos.
    largo = [m for m in metrics if not m.conclusive]
    if largo:
        pior = max(m.ci_width for m in largo)
        console.print(
            f"\n  [yellow]![/] O intervalo de confiança chega a {pior:.2f} de largura "
            f"com n={len(cases)}."
        )
        console.print(
            f"      Acima de {MAX_CI_WIDTH:.2f} o conjunto [bold]não distingue[/] os "
            f"modos: a diferença"
        )
        console.print(
            "      entre eles cabe dentro do ruído. Amplie o conjunto antes de concluir."
        )

    if any(m.by_class for m in metrics):
        console.print("\n  [bold]Recall@5 por classe[/]  [dim](acertos/consultas)[/]")
        for classe in sorted({k for m in metrics for k in m.by_class}):
            partes = [
                f"{m.mode} {m.by_class[classe][0]}/{m.by_class[classe][1]}"
                for m in metrics
                if classe in m.by_class
            ]
            console.print(f"    {classe:<16}{'   '.join(partes)}")
        for m in metrics:
            if m.no_answer_cases and m.no_answer_fp_rate is not None:
                console.print(
                    f"  [dim]sem resposta, {m.mode}: {m.no_answer_false_positives}/{m.no_answer_cases} com resultado "
                    f"tão bem pontuado quanto um acerto (falso positivo)[/]"
                )

    by_mode = {m.mode: m for m in metrics}
    if {"hybrid", "semantic", "keyword"} <= set(by_mode):
        h, s, k = by_mode["hybrid"], by_mode["semantic"], by_mode["keyword"]
        ok = h.recall_at_5 >= s.recall_at_5 and h.recall_at_5 >= k.recall_at_5
        mark = "[green]✓[/]" if ok else "[red]✗[/]"
        sufixo = "" if h.conclusive else "  [dim](inconclusivo — ver aviso acima)[/]"
        console.print(f"\n  {mark} híbrido {'>=' if ok else '<'} semântico e keyword{sufixo}")
        console.print(
            "  [dim]MRR é o indicador mais estável: usa a posição do primeiro acerto,[/]"
        )
        console.print(
            "  [dim]então não depende de quantos chunks do mesmo arquivo voltaram.[/]"
        )

    if show_failures:
        for m in metrics:
            if m.failures:
                console.print(f"\n  [yellow]{m.mode} — fora do top-5:[/]")
                for q, r in m.failures:
                    console.print(f"    {q!r}  [dim]rank={r or '—'}[/]")
    console.print()

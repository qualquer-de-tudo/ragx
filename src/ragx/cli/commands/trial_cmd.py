"""`ragx trial` — mede tokens de verdade: build_context vs. ler o arquivo inteiro.

Não é uma sessão de agente real reproduzida (isso exigiria instrumentar o
agente em si). É a comparação que dá pra fazer só com o que o RAGX controla —
o mesmo espírito do `ragx eval`, aplicado a economia de tokens em vez de
qualidade de ranking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.search.evaluation import load_cases
from ragx.search.trial import run_trial

console = Console()

CAVEAT = (
    'Isto é um proxy — compara com "ler o arquivo inteiro", não com uma '
    "sessão de agente real. Se a cobertura de fonte cair muito, a economia de "
    "token não vale nada: RAGX estaria economizando tokens jogando fora a resposta."
)


def trial_cmd(
    queries: Annotated[Path, typer.Option("--queries")] = Path("tests/eval/queries.yaml"),
    budget: Annotated[int, typer.Option("--budget")] = 3000,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compara tokens do build_context contra o baseline de ler o arquivo inteiro."""
    cfg = load_config()
    path = queries if queries.is_absolute() else cfg.root / queries
    cases = load_cases(path)
    results = run_trial(cfg, cases, budget=budget)

    total_baseline = sum(r.baseline_tokens for r in results)
    total_ragx = sum(r.ragx_tokens for r in results)
    total_hit = sum(r.sources_hit for r in results)
    total_sources = sum(r.sources_total for r in results)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "budget": budget,
                    "cases": len(results),
                    "results": [
                        {
                            "query": r.query,
                            "baseline_tokens": r.baseline_tokens,
                            "ragx_tokens": r.ragx_tokens,
                            "saved_tokens": r.saved_tokens,
                            "saved_ratio": round(r.saved_ratio, 4),
                            "sources_hit": r.sources_hit,
                            "sources_total": r.sources_total,
                        }
                        for r in results
                    ],
                    "totals": {
                        "baseline_tokens": total_baseline,
                        "ragx_tokens": total_ragx,
                        "saved_ratio": round(
                            (total_baseline - total_ragx) / total_baseline, 4
                        )
                        if total_baseline
                        else 0.0,
                        "source_coverage": round(total_hit / total_sources, 4)
                        if total_sources
                        else 0.0,
                    },
                    "caveat": CAVEAT,
                },
                ensure_ascii=False,
            )
        )
        return

    console.print(f"\n[bold]Trial de tokens[/] — {len(results)} consultas, orçamento {budget}\n")
    console.print(f"  {'Consulta':<40}{'Baseline':>10}{'RAGX':>8}{'Economia':>10}{'Fonte':>7}")
    console.print(f"  {'-' * 77}")
    for r in results:
        economia = f"{r.saved_ratio:.0%}"
        fonte = f"{r.sources_hit}/{r.sources_total}"
        console.print(
            f"  {r.query[:38]:<40}{r.baseline_tokens:>10}{r.ragx_tokens:>8}{economia:>10}{fonte:>7}"
        )

    coverage = total_hit / total_sources if total_sources else 0.0
    saved = (total_baseline - total_ragx) / total_baseline if total_baseline else 0.0
    console.print(f"\n  Total: {saved:.0%} menos tokens · fonte relevante coberta em {coverage:.0%} dos casos")
    console.print(f"\n  [dim]{CAVEAT}[/]\n")

"""`ragx trial` — compara tokens do build_context contra dois proxies de "sem RAGX"."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from ragx.config import load_config
from ragx.search.evaluation import load_cases
from ragx.search.trial import DEFAULT_GREP_FILES, auto_cases, conservative_ratio, run_trial

DEFAULT_QUERIES = Path("tests/eval/queries.yaml")

console = Console()

CAVEAT_LINES = (
    "São DOIS proxies, e nenhum é uma sessão de agente real. Oráculo: os arquivos",
    "certos, lidos inteiros. Grep~: os K primeiros arquivos de uma busca por palavra-",
    "chave, lidos inteiros. A economia mostrada é a CONSERVADORA (contra o menor dos",
    "dois). Não é a economia real: o número real vem de uma sessão de verdade (ragx ab).",
    "Se a cobertura de fonte cair muito, a economia de token não vale nada: o RAGX",
    "estaria economizando tokens jogando fora a resposta.",
)
CAVEAT = " ".join(CAVEAT_LINES)


def trial_cmd(
    queries: Annotated[
        Path,
        typer.Option(
            "--queries",
            help="Consultas de avaliação. Sem o arquivo padrão, gera consultas do próprio índice.",
        ),
    ] = DEFAULT_QUERIES,
    budget: Annotated[int, typer.Option("--budget")] = 3000,
    grep_files: Annotated[
        int,
        typer.Option("--grep-files", min=1, help="Arquivos que o 'Grep + Read' simulado lê inteiros."),
    ] = DEFAULT_GREP_FILES,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compara tokens do build_context contra dois baselines (oráculo e Grep simulado)."""
    cfg = load_config()
    path = queries if queries.is_absolute() else cfg.root / queries
    # Só o arquivo PADRÃO ausente vira geração automática: quem passou
    # `--queries` explícito e errou o caminho quer saber disso.
    auto = queries == DEFAULT_QUERIES and not path.is_file()
    if auto:
        cases = auto_cases(cfg)
        if not cases:
            from ragx.core.errors import UsageError

            raise UsageError(
                "sem tests/eval/queries.yaml e sem símbolos no índice para gerar consultas; "
                "indexe o projeto ou crie o arquivo"
            )
    else:
        cases = load_cases(path, only_answerable=True)
    results = run_trial(cfg, cases, budget=budget, grep_files=grep_files)

    total_baseline = sum(r.baseline_tokens for r in results)
    total_grep = sum(r.baseline_grep_tokens for r in results)
    total_ragx = sum(r.ragx_tokens for r in results)
    total_hit = sum(r.sources_hit for r in results)
    total_sources = sum(r.sources_total for r in results)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "budget": budget,
                    "cases": len(results),
                    "auto_generated": auto,
                    "results": [
                        {
                            "query": r.query,
                            "baseline_tokens": r.baseline_tokens,
                            "baseline_oracle_tokens": r.baseline_oracle_tokens,
                            "baseline_grep_tokens": r.baseline_grep_tokens,
                            "ragx_tokens": r.ragx_tokens,
                            "saved_tokens": r.saved_tokens,
                            "saved_ratio": round(r.saved_ratio, 4),
                            "saved_ratio_conservative": round(r.saved_ratio_conservative, 4),
                            "sources_hit": r.sources_hit,
                            "sources_total": r.sources_total,
                            "missing_paths": r.missing_paths,
                        }
                        for r in results
                    ],
                    "totals": {
                        "grep_files": grep_files,
                        "baseline_tokens": total_baseline,
                        "baseline_oracle_tokens": total_baseline,
                        "baseline_grep_tokens": total_grep,
                        "saved_ratio_conservative": round(
                            conservative_ratio(total_baseline, total_grep, total_ragx), 4
                        ),
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
    if auto:
        console.print("  [dim]Sem tests/eval/queries.yaml: consultas geradas dos símbolos do índice.[/]\n")
    console.print(
        f"  {'Consulta':<36}{'Oráculo':>9}{'Grep~':>8}{'RAGX':>7}{'Econ. cons.':>13}{'Fonte':>7}"
    )
    console.print(f"  {'-' * 80}")
    for r in results:
        economia = f"{r.saved_ratio_conservative:.0%}"
        fonte = f"{r.sources_hit}/{r.sources_total}"
        consulta = escape(f"{r.query[:34]:<36}")
        console.print(
            f"  {consulta}{r.baseline_tokens:>9}{r.baseline_grep_tokens:>8}"
            f"{r.ragx_tokens:>7}{economia:>13}{fonte:>7}"
        )
        if r.missing_paths:
            console.print(
                f"    [yellow]aviso:[/] {r.missing_paths} caminho(s) em relevant_paths "
                "não encontrado(s) — corpus desatualizado, não contado no baseline"
            )

    coverage = total_hit / total_sources if total_sources else 0.0
    saved = conservative_ratio(total_baseline, total_grep, total_ragx)
    direcao = "menos" if saved >= 0 else "mais"
    console.print(
        f"\n  Total (conservador, contra o menor baseline): {abs(saved):.0%} {direcao} tokens "
        f"· fonte relevante coberta em {coverage:.0%} dos casos"
    )
    console.print()
    for line in CAVEAT_LINES:
        console.print(f"  [dim]{line}[/]")
    console.print()

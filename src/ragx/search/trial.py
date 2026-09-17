"""Comparação honesta: tokens que o build_context entrega vs. o baseline de
ler o arquivo inteiro. Mede o que o `ragx eval` não mede — economia real de
tokens, não qualidade de ranking. Reusa o mesmo corpus de `evaluation.py`.

Isto é um proxy, não uma sessão de agente real replayed. Ver docs/07 e o
aviso impresso por `ragx trial`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragx.config import Config
from ragx.context.engine import build_context
from ragx.search.evaluation import EvalCase
from ragx.tokens import get_counter


@dataclass
class TrialResult:
    query: str
    baseline_tokens: int
    ragx_tokens: int
    sources_hit: int
    sources_total: int
    missing_paths: int = 0

    @property
    def saved_tokens(self) -> int:
        return self.baseline_tokens - self.ragx_tokens

    @property
    def saved_ratio(self) -> float:
        if self.baseline_tokens <= 0:
            return 0.0
        return self.saved_tokens / self.baseline_tokens


def run_trial(cfg: Config, cases: list[EvalCase], budget: int = 3000) -> list[TrialResult]:
    counter = get_counter()
    out: list[TrialResult] = []
    for case in cases:
        baseline = 0
        missing_paths = 0
        for rel in case.relevant_paths:
            fp = cfg.root / rel
            if fp.is_file():
                baseline += counter.count(fp.read_text(encoding="utf-8", errors="ignore"))
            else:
                missing_paths += 1
        pack = build_context(cfg, case.query, budget=budget, use_cache=False)
        hit_paths = {f.document_path for f in pack.fragments}
        sources_hit = sum(1 for rel in case.relevant_paths if rel in hit_paths)
        out.append(
            TrialResult(
                query=case.query,
                baseline_tokens=baseline,
                ragx_tokens=pack.estimated_tokens,
                sources_hit=sources_hit,
                sources_total=len(case.relevant_paths),
                missing_paths=missing_paths,
            )
        )
    return out

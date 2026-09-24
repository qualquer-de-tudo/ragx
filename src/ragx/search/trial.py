"""Comparação honesta: tokens que o build_context entrega vs. o baseline de
ler o arquivo inteiro. Mede o que o `ragx eval` não mede — economia real de
tokens, não qualidade de ranking. Reusa o mesmo corpus de `evaluation.py`.

Isto é um proxy, não uma sessão de agente real replayed. Ver docs/07 e o
aviso impresso por `ragx trial`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


_NOT_TEST = """
    d.rel_path NOT LIKE 'test%' AND d.rel_path NOT LIKE '%/test%'
    AND d.rel_path NOT LIKE '%.test.%' AND d.rel_path NOT LIKE '%.spec.%'
    AND d.rel_path NOT LIKE '%migration%'
"""


def auto_cases(cfg: Config, limit: int = 8) -> list[EvalCase]:
    """Consultas geradas do próprio índice, para projeto sem `queries.yaml`.

    Cada caso é "como funciona <nome>" com o arquivo que o define como fonte
    esperada, sempre de código fora de testes e com nome que aparece uma vez
    só (um `status` definido em cinco lugares não tem fonte certa).

    Com grafo, os nomes são classes e funções, das mais conectadas para as
    menos. Sem grafo (nunca gerado, ou linguagem sem extrator), são os nomes
    dos arquivos de código de tamanho médio: grandes demais costumam ser
    gerados, pequenos demais não têm o que economizar.
    """
    from ragx.storage.db import open_db

    with open_db(cfg.db_path, read_only=True) as conn:
        rows = conn.execute(
            f"""
            SELECT e.name, d.rel_path,
                   (SELECT COUNT(*) FROM relations r WHERE r.src_id = e.id OR r.dst_id = e.id) AS grau
            FROM entities e JOIN documents d ON d.id = e.document_id
            WHERE e.type IN ('class', 'function') AND d.doc_kind = 'code'
              AND LENGTH(e.name) >= 4 AND {_NOT_TEST}
              AND (SELECT COUNT(*) FROM entities o
                   WHERE o.name = e.name AND o.type IN ('class', 'function')) = 1
            ORDER BY (e.type = 'class') DESC, grau DESC, e.name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        pairs = [(name, path) for name, path, _ in rows]
        if not pairs:
            docs = conn.execute(
                f"""
                SELECT d.rel_path FROM documents d
                WHERE d.doc_kind = 'code' AND d.size_bytes BETWEEN 1500 AND 60000 AND {_NOT_TEST}
                ORDER BY d.size_bytes DESC
                """
            ).fetchall()
            vistos: dict[str, str | None] = {}
            for (rel,) in docs:
                stem = Path(rel).stem.split(".")[0]
                if len(stem) < 4 or stem.lower() in ("index", "main", "types", "utils"):
                    continue
                vistos[stem] = None if stem in vistos else rel
            pairs = [(stem, rel) for stem, rel in vistos.items() if rel is not None][:limit]
    return [EvalCase(query=f"como funciona {name}", relevant_paths=(path,)) for name, path in pairs]

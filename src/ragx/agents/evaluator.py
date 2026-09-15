"""`ragx agent eval` — mede RECUPERAÇÃO, não geração.

É honesto: o RAGX não avalia a qualidade da resposta do modelo, avalia se
entregou o contexto certo. Avaliar geração exigiria LLM-as-judge, registrado
como evolução pós-MVP.

Ver docs/10-agent-training.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from ragx.agents.profile import load
from ragx.config import Config
from ragx.context.engine import build_context
from ragx.core.errors import UsageError
from ragx.storage.db import utcnow


@dataclass
class CaseResult:
    id: str
    task: str
    passed: bool
    rank: int | None = None
    sources: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    name: str = ""
    results: list[CaseResult] = field(default_factory=list)
    recall_at_3: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)


def evaluate(cfg: Config, name: str, case_id: str | None = None) -> EvalReport:
    manifest, paths = load(cfg, name)
    path = paths.evaluation / "cases.yaml"
    if not path.is_file():
        raise UsageError(f"perfil {name} não tem evaluation/cases.yaml")

    cases = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if case_id:
        cases = [c for c in cases if c.get("id") == case_id]
        if not cases:
            raise UsageError(f"caso não encontrado: {case_id}")

    report = EvalReport(name=name)
    hits = 0
    for case in cases:
        result = _run_case(cfg, manifest, case)
        report.results.append(result)
        if result.rank is not None and result.rank <= 3:
            hits += 1
    report.recall_at_3 = hits / max(len(cases), 1)

    out = paths.evaluation / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.yaml").write_text(
        yaml.safe_dump(
            {
                "generated_at": utcnow(),
                "recall_at_3": round(report.recall_at_3, 4),
                "passed": report.passed,
                "total": len(report.results),
                "cases": [
                    {"id": r.id, "passed": r.passed, "rank": r.rank, "failures": r.failures}
                    for r in report.results
                ],
            },
            allow_unicode=True,
            sort_keys=True,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return report


def _run_case(cfg: Config, manifest: Any, case: dict[str, Any]) -> CaseResult:
    task = case.get("task", "")
    result = CaseResult(id=case.get("id", "?"), task=task, passed=True)

    pack = build_context(
        cfg, task, budget=manifest.context_policy.default_tokens,
        depth=manifest.context_policy.graph_depth, use_cache=False,
    )
    result.sources = list(pack.sources)
    corpo = "\n".join(f.content for f in pack.fragments).lower()

    esperadas = case.get("expect_sources") or []
    if esperadas:
        for i, src in enumerate(result.sources, start=1):
            if src in esperadas:
                result.rank = i
                break
        if result.rank is None:
            result.passed = False
            result.failures.append(f"fonte esperada ausente: {esperadas}")
        elif result.rank > 3:
            result.passed = False
            result.failures.append(f"fonte esperada em posição {result.rank} (esperado <= 3)")

    for termo in case.get("must_mention") or []:
        if termo.lower() not in corpo:
            result.passed = False
            result.failures.append(f"não mencionou: {termo}")

    for termo in case.get("must_not_mention") or []:
        if termo.lower() in corpo:
            result.passed = False
            result.failures.append(f"mencionou o proibido: {termo}")

    projeto = case.get("expect_project")
    if projeto:
        projetos = {f.project for f in pack.fragments}
        if projeto not in projetos:
            result.passed = False
            result.failures.append(f"projeto esperado ausente: {projeto}")

    skill = case.get("expect_skill")
    if skill:
        _m, paths = load(cfg, manifest.name)
        if not (paths.skills / f"{skill}.md").is_file():
            result.passed = False
            result.failures.append(f"skill esperada não existe: {skill}")

    return result

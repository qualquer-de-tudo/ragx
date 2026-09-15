"""Tipos do domínio de orquestração.

Sem infraestrutura aqui dentro: nada de sqlite3, yaml, typer ou rich. A máquina
de estados vive neste módulo porque é regra, não persistência — e o repositório
a consulta antes de gravar qualquer transição.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar


class Status(StrEnum):
    PENDING = "pending"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    FAILED = "failed"
    RETRYING = "retrying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


#: Transições permitidas. O que não está aqui é RECUSADO pelo repositório —
#: `COMPLETED -> RUNNING` levanta erro em vez de acontecer em silêncio.
TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.PENDING: frozenset({Status.READY, Status.BLOCKED, Status.CANCELLED,
                               Status.SKIPPED}),
    Status.READY: frozenset({Status.QUEUED, Status.BLOCKED, Status.PENDING,
                             Status.CANCELLED, Status.SKIPPED}),
    Status.QUEUED: frozenset({Status.RUNNING, Status.READY, Status.FAILED,
                              Status.CANCELLED, Status.WAITING_APPROVAL}),
    Status.RUNNING: frozenset({Status.COMPLETED, Status.FAILED, Status.BLOCKED,
                               Status.WAITING_APPROVAL, Status.CANCELLED,
                               Status.READY}),
    Status.BLOCKED: frozenset({Status.PENDING, Status.READY, Status.CANCELLED,
                               Status.SKIPPED}),
    Status.WAITING_APPROVAL: frozenset({Status.READY, Status.RUNNING,
                                        Status.CANCELLED, Status.SKIPPED,
                                        Status.FAILED}),
    Status.FAILED: frozenset({Status.RETRYING, Status.READY, Status.CANCELLED,
                              Status.SKIPPED}),
    Status.RETRYING: frozenset({Status.READY, Status.FAILED, Status.CANCELLED}),
    # Terminais. `cancelled` é decisão humana e não se desfaz sozinha.
    Status.COMPLETED: frozenset({Status.READY}),  # reabertura explícita
    Status.CANCELLED: frozenset(),
    Status.SKIPPED: frozenset({Status.PENDING}),
}

#: Precedência para resolver conflito de merge em `status` (ADR-0014).
#: O estado mais avançado ganha — exceto `cancelled`, que sobrepõe tudo.
STATUS_PRECEDENCE: tuple[Status, ...] = (
    Status.PENDING, Status.READY, Status.QUEUED, Status.BLOCKED,
    Status.WAITING_APPROVAL, Status.RUNNING, Status.RETRYING,
    Status.FAILED, Status.COMPLETED, Status.CANCELLED,
)

TERMINAL = frozenset({Status.COMPLETED, Status.CANCELLED, Status.SKIPPED})
#: Uma dependência nestes estados não impede a dependente de ficar pronta.
SATISFYING = frozenset({Status.COMPLETED, Status.SKIPPED})

PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Classification(StrEnum):
    DIRECT_EXECUTION = "DIRECT_EXECUTION"
    ANALYSIS_REQUIRED = "ANALYSIS_REQUIRED"
    DOCUMENTATION_REQUIRED = "DOCUMENTATION_REQUIRED"
    TASK_DECOMPOSITION_REQUIRED = "TASK_DECOMPOSITION_REQUIRED"
    ARCHITECTURAL_CHANGE = "ARCHITECTURAL_CHANGE"
    PRODUCT_CHANGE = "PRODUCT_CHANGE"
    SECURITY_CHANGE = "SECURITY_CHANGE"
    PERFORMANCE_CHANGE = "PERFORMANCE_CHANGE"
    UNKNOWN = "UNKNOWN"


class DependencyKind(StrEnum):
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    BLOCKED_BY = "blocked_by"
    PARENT = "parent"
    CHILD = "child"
    RELATED_TO = "related_to"


#: Só estas afetam prontidão. `related_to` é navegação, não ordem.
BLOCKING_KINDS = frozenset(
    {DependencyKind.DEPENDS_ON, DependencyKind.BLOCKED_BY, DependencyKind.PARENT}
)


class EventType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    TASK_READY = "TASK_READY"
    TASK_CLAIMED = "TASK_CLAIMED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_RELEASED = "TASK_RELEASED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    KNOWLEDGE_UPDATED = "KNOWLEDGE_UPDATED"
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
    GIT_MERGED = "GIT_MERGED"
    AGENT_FINISHED = "AGENT_FINISHED"
    SCHEDULE_FIRED = "SCHEDULE_FIRED"


@dataclass(frozen=True, slots=True)
class Scores:
    complexity: int = 0
    architecture: int = 0
    business_rule: int = 0
    dependency: int = 0
    risk: int = 0
    security: int = 0
    documentation: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "complexity": self.complexity, "architecture": self.architecture,
            "business_rule": self.business_rule, "dependency": self.dependency,
            "risk": self.risk, "security": self.security,
            "documentation": self.documentation,
        }

    #: Peso relativo de cada dimensão. Arquitetura pesa mais porque é o que mais
    #: prevê retrabalho; documentação pesa menos porque é consequência, não causa.
    WEIGHTS: ClassVar[dict[str, float]] = {
        "complexity": 1.2, "architecture": 1.3, "business_rule": 1.0,
        "dependency": 0.9, "risk": 1.1, "security": 1.0, "documentation": 0.8,
    }

    @property
    def total(self) -> int:
        """Pico + média dos ativos + amplitude. Nem soma, nem média simples.

        **Soma** faria qualquer pedido com quatro palavras virar projeto.

        **Média sobre as 7 dimensões** é pior e menos óbvio: as dimensões
        zeradas afundam o resultado. Um pedido que crava 60 em arquitetura,
        segurança e negócio — inequivocamente um projeto — sairia perto de 30,
        porque quatro dimensões irrelevantes votaram zero.

        Então: o PICO manda (a maior preocupação define o piso), a média entre
        as dimensões que realmente dispararam ajusta, e a AMPLITUDE — quantas
        preocupações distintas apareceram — é o que separa "uma coisa difícil"
        de "um projeto".
        """
        d = self.as_dict()
        ativos = [k for k, v in d.items() if v > 0]
        if not ativos:
            return 0
        maior_peso = max(self.WEIGHTS.values())
        pico = max(d[k] * self.WEIGHTS[k] for k in ativos) / maior_peso
        media = sum(d[k] * self.WEIGHTS[k] for k in ativos) / sum(
            self.WEIGHTS[k] for k in ativos
        )
        amplitude = len(ativos) / len(d)
        return round(min(100.0, 0.55 * pico + 0.20 * media + 30.0 * amplitude))


@dataclass
class Analysis:
    request: str = ""
    classification: Classification = Classification.UNKNOWN
    complexity: str = "low"
    requires_documentation: bool = False
    requires_decomposition: bool = False
    requires_approval: bool = False
    confidence: float = 0.0
    reasoning_summary: str = ""
    risks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    scores: Scores = field(default_factory=Scores)
    #: Total EFETIVO usado na decisao (0 quando o pedido e' trivial), que pode
    #: diferir de `scores.total` — quem lê o relatório precisa ver o que
    #: realmente decidiu, não o que teria decidido sem as regras de redução.
    total: int = 0
    strategy: str = "EXECUTE"
    matched: list[str] = field(default_factory=list)
    overridden_by: str | None = None
    override_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": str(self.classification),
            "complexity": self.complexity,
            "requires_documentation": self.requires_documentation,
            "requires_decomposition": self.requires_decomposition,
            "requires_approval": self.requires_approval,
            "confidence": round(self.confidence, 2),
            "reasoning_summary": self.reasoning_summary,
            "risks": list(self.risks),
            "dependencies": list(self.dependencies),
            "scores": {**self.scores.as_dict(), "total": self.total,
                       "raw_total": self.scores.total},
            "strategy": self.strategy,
            "matched_signals": list(self.matched),
            "overridden_by": self.overridden_by,
            "override_reason": self.override_reason,
        }


@dataclass
class Task:
    id: str = ""
    project_id: str = ""
    parent_task_id: str | None = None
    seq: int = 0
    title: str = ""
    description: str = ""
    type: str = "technical"
    track: str = "backend"
    status: Status = Status.PENDING
    priority: str = "medium"
    complexity: str = "medium"
    acceptance_criteria: list[str] = field(default_factory=list)
    required_context: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    files_scope: list[str] = field(default_factory=list)
    security_requirements: list[str] = field(default_factory=list)
    performance_requirements: list[str] = field(default_factory=list)
    test_requirements: list[str] = field(default_factory=list)
    agent: str | None = None
    requires_approval: bool = False
    dependencies: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    @property
    def priority_rank(self) -> int:
        return PRIORITY_RANK.get(self.priority, 1)


@dataclass
class TaskResult:
    """O que o agente devolve. Espelha a §19 do pedido."""

    status: str = "completed"
    summary: str = ""
    changes: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    security_review: dict[str, Any] = field(default_factory=dict)
    performance_review: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    knowledge_updates: list[str] = field(default_factory=list)
    remaining_risks: list[str] = field(default_factory=list)
    next_tasks: list[str] = field(default_factory=list)
    acceptance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskResult:
        conhecidos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in conhecidos})

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "summary": self.summary,
            "changes": self.changes, "files_changed": self.files_changed,
            "tests": self.tests, "security_review": self.security_review,
            "performance_review": self.performance_review,
            "decisions": self.decisions, "knowledge_updates": self.knowledge_updates,
            "remaining_risks": self.remaining_risks, "next_tasks": self.next_tasks,
            "acceptance": self.acceptance,
        }


@dataclass
class Validation:
    ok: bool = True
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, motivo: str) -> None:
        self.ok = False
        self.failures.append(motivo)


class InvalidTransitionError(Exception):
    def __init__(self, task_id: str, origem: Status, destino: Status):
        super().__init__(
            f"{task_id}: transição inválida {origem} -> {destino}. "
            f"De {origem} só é possível ir para "
            f"{sorted(str(s) for s in TRANSITIONS.get(origem, frozenset())) or 'nenhum estado'}"
        )
        self.task_id, self.origem, self.destino = task_id, origem, destino


class CycleError(Exception):
    def __init__(self, caminho: list[str]):
        super().__init__("ciclo: " + " → ".join(caminho))
        self.caminho = caminho


def can_transition(origem: Status, destino: Status) -> bool:
    if origem == destino:
        return True
    return destino in TRANSITIONS.get(origem, frozenset())


def merge_status(local: Status, remoto: Status) -> Status:
    """Resolve conflito de merge: o estado mais avançado ganha (ADR-0014)."""
    ordem = {s: i for i, s in enumerate(STATUS_PRECEDENCE)}
    return max(local, remoto, key=lambda s: ordem.get(s, -1))

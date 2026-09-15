"""Modelos de domínio. Dataclasses frozen+slots: o domínio não paga custo de
validação em objeto criado milhões de vezes (ver ADR-0001)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[self.value]


class Action(StrEnum):
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"


class Verdict(StrEnum):
    ALLOW = "allow"
    ALLOW_REDACTED = "allow_redacted"
    SKIP = "skip"  # ignorado por .gitignore/.ragignore — NÃO é incidente
    BLOCK = "block"  # bloqueado por política de segurança — É incidente


class DocKind(StrEnum):
    CODE = "code"
    DOC = "doc"
    CONFIG = "config"
    DATA = "data"


class ChunkKind(StrEnum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    SECTION = "section"
    STATEMENT = "statement"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    """O valor do segredo NUNCA entra aqui. Só digest e preview mascarado."""

    rule_id: str
    severity: Severity
    action: Action
    path: str
    line: int
    column: int = 0
    digest: str = ""
    preview: str = ""
    detected_by: str = "pattern"


@dataclass(frozen=True, slots=True)
class GateDecision:
    verdict: Verdict
    path: str
    rule_id: str | None = None
    findings: tuple[SecurityFinding, ...] = ()
    content: str | None = None  # None em SKIP/BLOCK
    reason: str = ""

    @property
    def admitted(self) -> bool:
        return self.verdict in (Verdict.ALLOW, Verdict.ALLOW_REDACTED)


@dataclass(frozen=True, slots=True)
class ParseNode:
    kind: ChunkKind
    start_line: int
    end_line: int
    symbol: str | None = None
    children: tuple[ParseNode, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseResult:
    nodes: tuple[ParseNode, ...] = ()
    lang: str = "text"
    doc_kind: DocKind = DocKind.DOC
    degraded: bool = False
    title: str | None = None


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    document_id: str
    ordinal: int
    kind: ChunkKind
    start_line: int
    end_line: int
    content: str
    content_hash: str
    token_count: int
    symbol: str | None = None
    heading_path: str | None = None
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    rel_path: str
    doc_kind: DocKind
    size_bytes: int
    mtime_ns: int
    content_hash: str
    chunker_version: str
    lang: str | None = None
    title: str | None = None
    redacted: bool = False


@dataclass(frozen=True, slots=True)
class FileCandidate:
    rel_path: str
    size_bytes: int
    mtime_ns: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_id: str
    document_path: str
    kind: ChunkKind
    start_line: int
    end_line: int
    score: float
    content: str
    project: str = "current"
    symbol: str | None = None
    heading_path: str | None = None
    matched_by: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexStats:
    files_seen: int = 0
    indexed: int = 0
    unchanged: int = 0
    skipped: int = 0
    blocked: int = 0
    redacted: int = 0
    removed: int = 0
    chunks: int = 0
    embedded: int = 0
    duration_ms: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)

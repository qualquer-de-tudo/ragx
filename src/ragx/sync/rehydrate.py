"""Reidratação: reconstrói o conteúdo dos chunks a partir do working tree.

É o mecanismo que permite não versionar conteúdo. Três propriedades:

  1. AUTOVERIFICAÇÃO — reidratação errada é impossível passar despercebida:
     o hash não bate e o documento é reprocessado.
  2. CONVERGÊNCIA — `knowledge/` desatualizado não corrompe nada.
  3. OFFLINE — nenhuma etapa precisa de rede nem de embedder.

Este é o SEGUNDO (e último) módulo autorizado a ler o filesystem do
projeto-alvo. Ver ADR-0008 e ADR-0010.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ragx.config import Config
from ragx.core.ids import content_hash, normalize_text
from ragx.security.gate import SecurityGate
from ragx.sync import serialize


class RehydrateStatus(StrEnum):
    OK = "ok"
    HASH_MISMATCH = "hash_mismatch"
    FILE_MISSING = "file_missing"
    BLOCKED = "blocked"


@dataclass
class RehydrateReport:
    total: int = 0
    ok: int = 0
    mismatch: int = 0
    missing: int = 0
    blocked: int = 0
    synthetic: int = 0  # chunk que não é fatia literal (cabeçalho de classe, fusão)
    rederive: set[str] = field(default_factory=set)
    dropped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.mismatch == 0 and self.missing == 0


@dataclass(frozen=True, slots=True)
class Hydrated:
    chunk_id: str
    rel_path: str
    start_line: int
    end_line: int
    content: str
    content_hash: str
    status: RehydrateStatus


def rehydrate(
    cfg: Config, out_dir: str = "knowledge"
) -> tuple[list[Hydrated], RehydrateReport]:
    report = RehydrateReport()
    out: list[Hydrated] = []
    gate = SecurityGate(
        cfg.root, policy=cfg.security.policy, scan_content=cfg.security.scan_content
    )
    cache: dict[str, list[str] | None] = {}

    for doc in serialize.read_documents(cfg, out_dir):
        rel = doc["rel_path"]
        chunks = serialize.read_chunks(cfg, rel, out_dir)
        if not chunks:
            continue

        lines = _lines(cfg.root, rel, gate, cache)
        if lines is None:
            report.total += len(chunks)
            report.missing += len(chunks)
            for c in chunks:
                report.dropped.append((c["id"], RehydrateStatus.FILE_MISSING.value))
            continue
        if lines is _BLOCKED:
            report.total += len(chunks)
            report.blocked += len(chunks)
            report.rederive.add(rel)
            for c in chunks:
                report.dropped.append((c["id"], RehydrateStatus.BLOCKED.value))
            continue

        derived: dict[str, str] | None = None
        for c in chunks:
            report.total += 1
            start, end = c["lines"]
            text = "\n".join(lines[max(start - 1, 0) : end])
            got = content_hash(text)

            if got == c["content_hash"]:
                report.ok += 1
                out.append(
                    Hydrated(c["id"], rel, start, end, normalize_text(text), got,
                             RehydrateStatus.OK)
                )
                continue

            # Nem todo chunk é fatia literal do arquivo: o cabeçalho de classe
            # ganha a lista de métodos, e chunks minúsculos são fundidos. Para
            # esses, a verificação correta é o próprio pipeline determinístico,
            # não o corte de linhas.
            if derived is None:
                derived = _rechunk(cfg, rel, lines)
            rebuilt = derived.get(c["id"])
            if rebuilt is not None:
                report.ok += 1
                report.synthetic += 1
                out.append(
                    Hydrated(c["id"], rel, start, end, rebuilt, c["content_hash"],
                             RehydrateStatus.OK)
                )
            else:
                report.mismatch += 1
                report.rederive.add(rel)

    return out, report


def _rechunk(cfg: Config, rel: str, lines: list[str]) -> dict[str, str]:
    """Reconstrói os chunks do documento pelo pipeline. Determinístico: os ids
    batem com os do índice sempre que o arquivo não mudou."""
    from ragx.indexing import parsers
    from ragx.indexing.chunkers import ChunkOptions, chunk_document

    text = "\n".join(lines)
    parsed = parsers.parse(rel, text, include_unknown=cfg.index.include_unknown)
    if parsed is None:
        return {}
    opts = ChunkOptions(max_tokens=cfg.chunk.max_tokens, min_tokens=cfg.chunk.min_tokens)
    return {c.id: c.content for c in chunk_document(rel, text, parsed, opts)}


_BLOCKED: list[str] = []  # sentinela: arquivo existe mas foi bloqueado pelo gate


def _lines(
    root: Path, rel: str, gate: SecurityGate, cache: dict[str, list[str] | None]
) -> list[str] | None:
    if rel in cache:
        return cache[rel]
    path = root / rel
    try:
        raw = path.read_bytes()
    except OSError:
        cache[rel] = None
        return None
    # Re-scan no sync: arquivo já indexado pode ter VIRADO sensível.
    decision = gate.admit(rel, raw)
    if not decision.admitted or decision.content is None:
        cache[rel] = _BLOCKED
        return _BLOCKED
    lines = decision.content.splitlines()
    cache[rel] = lines
    return lines

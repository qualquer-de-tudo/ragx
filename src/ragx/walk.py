"""FileWalker — um dos DOIS únicos pontos autorizados a ler o filesystem do
projeto-alvo (o outro é sync/incremental). Todo byte lido sai daqui já tendo
passado pelo SecurityGate.

Ver docs/04-indexacao.md e ADR-0008.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from ragx.core.models import GateDecision, Verdict
from ragx.security.gate import SecurityGate

_BINARY_PROBE = 8192


@dataclass(frozen=True, slots=True)
class WalkedFile:
    rel_path: str
    size_bytes: int
    mtime_ns: int
    decision: GateDecision
    unchanged: bool = False

    @property
    def content(self) -> str | None:
        return self.decision.content


def iter_files(
    root: Path,
    gate: SecurityGate,
    max_bytes: int = 1_048_576,
    follow_symlinks: bool = False,
    only: set[str] | None = None,
    fingerprints: dict[str, tuple[int, int]] | None = None,
    prefix: str = "",
) -> Iterator[WalkedFile]:
    """Emite candidatos em streaming — nunca carrega o repositório em memória.

    `prefix` namespaceia a árvore no índice (conhecimento base entra como
    `@base/<fonte>/...`). O gate continua vendo o caminho REAL dentro da raiz,
    para que regra de nome e .gitignore funcionem igual; o prefixo só existe
    do lado de fora.
    """
    root = Path(root).resolve()
    visited: set[tuple[int, int]] = set()

    for path in _walk(root, follow_symlinks, visited):
        inner = path.relative_to(root).as_posix()
        rel = prefix + inner
        if only is not None and rel not in only:
            continue
        try:
            st = path.stat()
        except OSError:
            continue

        # Ignore antes de ler: o arquivo grande ignorado não custa I/O.
        ignored, source = gate.ignore.should_ignore(inner)
        if ignored:
            yield WalkedFile(
                rel, st.st_size, st.st_mtime_ns,
                GateDecision(Verdict.SKIP, rel, rule_id=source, reason="ignore"),
            )
            continue

        # Atalho: size+mtime idênticos ao registrado -> nem abre o arquivo.
        # É o que faz a reindexação sem mudanças ser barata (docs/04-indexacao.md).
        if fingerprints is not None:
            fp = fingerprints.get(rel)
            if fp is not None and fp == (st.st_size, st.st_mtime_ns):
                yield WalkedFile(
                    rel, st.st_size, st.st_mtime_ns,
                    GateDecision(Verdict.ALLOW, rel, reason="unchanged"),
                    unchanged=True,
                )
                continue

        if st.st_size > max_bytes:
            yield WalkedFile(
                rel, st.st_size, st.st_mtime_ns,
                GateDecision(Verdict.SKIP, rel, rule_id="too_large", reason="too_large"),
            )
            continue

        # Deny-list de nome ANTES de abrir o arquivo.
        hit = gate.scanner.scan_filename(inner)
        if hit is not None:
            yield WalkedFile(
                rel, st.st_size, st.st_mtime_ns,
                GateDecision(Verdict.BLOCK, rel, rule_id=hit.rule_id, findings=(hit,),
                             reason=hit.rule_id),
            )
            continue

        try:
            raw = path.read_bytes()
        except OSError:
            continue

        if b"\x00" in raw[:_BINARY_PROBE]:
            yield WalkedFile(
                rel, st.st_size, st.st_mtime_ns,
                GateDecision(Verdict.SKIP, rel, rule_id="binary", reason="binary"),
            )
            continue

        decision = gate.admit(inner, raw)
        if prefix:
            decision = replace(decision, path=rel)
        yield WalkedFile(rel, st.st_size, st.st_mtime_ns, decision)


def scan_fingerprints(
    root: Path, gate: SecurityGate, follow_symlinks: bool = False
) -> dict[str, tuple[int, int]]:
    """`{caminho: (tamanho, mtime_ns)}` — sem abrir um único arquivo.

    É o que o `ragx watch` compara entre dois instantes. Fica aqui, e não no
    watcher, para que continue valendo que só este módulo enumera o projeto:
    o watcher recebe nomes e números, nunca bytes.
    """
    root = Path(root).resolve()
    visited: set[tuple[int, int]] = set()
    out: dict[str, tuple[int, int]] = {}
    for path in _walk(root, follow_symlinks, visited):
        rel = path.relative_to(root).as_posix()
        ignored, _ = gate.ignore.should_ignore(rel)
        if ignored:
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        out[rel] = (st.st_size, st.st_mtime_ns)
    return out


def _walk(
    root: Path, follow_symlinks: bool, visited: set[tuple[int, int]]
) -> Iterator[Path]:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in sorted(entries):
            try:
                if entry.is_symlink():
                    if not follow_symlinks:
                        continue
                    # Symlink que escapa da raiz é recusado (ameaça A8).
                    target = entry.resolve()
                    if not target.is_relative_to(root):
                        continue
                if entry.is_dir():
                    st = entry.stat()
                    key = (st.st_dev, st.st_ino)
                    if key in visited:  # ciclo
                        continue
                    visited.add(key)
                    stack.append(entry)
                elif entry.is_file():
                    yield entry
            except OSError:
                continue

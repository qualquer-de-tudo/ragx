"""Pipeline de indexação incremental.

walker -> gate -> parser -> chunker -> store

Transação por LOTE (não uma gigante): Ctrl+C deixa o banco consistente com os
lotes já confirmados. Ver docs/04-indexacao.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ragx import gitinfo
from ragx.base import source as base_source
from ragx.config import Config
from ragx.core.errors import IndexBusyError, UsageError
from ragx.core.ids import CHUNKER_VERSION, content_hash, document_id
from ragx.core.models import Document, IndexStats, Verdict
from ragx.indexing import lock, parsers
from ragx.indexing.chunkers import ChunkOptions, chunk_document
from ragx.indexing.embed import embed_pending
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db, set_meta
from ragx.storage.repositories import ChunkRepo, DocumentRepo, RunRepo, SecurityEventRepo
from ragx.walk import WalkedFile, iter_files

VALID_SOURCES = frozenset({
    "cli", "panel", "watch", "sync", "mcp:refresh", "mcp:index",
    "hook:post-checkout", "hook:post-commit", "hook:post-merge",
})


class _EmbedOnlyDoneError(Exception):
    """Controle de fluxo interno: --embed-only pula a varredura."""


@dataclass
class IndexReport:
    stats: IndexStats = field(default_factory=IndexStats)
    blocked_paths: list[str] = field(default_factory=list)
    new_documents: int = 0
    modified_documents: int = 0
    new_chunks: int = 0
    degraded: int = 0
    interrupted: bool = False
    embed_error: str | None = None


MAX_PENDING_RERUNS = 3


def index_project(
    cfg: Config,
    full: bool = False,
    dry_run: bool = False,
    progress: Callable[[int, str], None] | None = None,
    embed: bool = True,
    embed_only: bool = False,
    source: str = "cli",
    wait_s: float = 0.0,
) -> IndexReport:
    if source not in VALID_SOURCES:
        raise UsageError(f"origem desconhecida: {source}")
    if dry_run:
        return _index_once(cfg, full, dry_run, progress, embed, embed_only, source)

    state_dir = cfg.state_dir
    deadline = time.monotonic() + max(wait_s, 0.0)
    while not lock.try_acquire(state_dir, "index", source):
        if time.monotonic() >= deadline:
            current = lock.holder(state_dir)
            lock.mark_pending(state_dir, source)
            # Entre marcar o pedido e chegar aqui o dono pode ter liberado a
            # trava; tenta mais uma vez antes de desistir. Sem isso o pedido
            # fica órfão: ninguém mais vai drená-lo.
            if not lock.try_acquire(state_dir, "index", source):
                raise IndexBusyError(current)
            break
        time.sleep(0.5)

    budget = MAX_PENDING_RERUNS
    try:
        report = _index_once(cfg, full, dry_run, progress, embed, embed_only, source)
        budget = _drain_pending(cfg, state_dir, budget)
        return report
    finally:
        lock.release(state_dir)
        # Um pedido pode ter chegado entre o último take_pending acima e o
        # release: reobtém a trava uma vez e drena de novo antes de devolver
        # o controle. O orçamento de reexecuções é o mesmo da primeira
        # drenagem — não reinicia.
        if lock.is_pending(state_dir) and lock.try_acquire(state_dir, "index", source):
            try:
                _drain_pending(cfg, state_dir, budget)
            finally:
                lock.release(state_dir)


def _drain_pending(cfg: Config, state_dir: Path, budget: int) -> int:
    """Roda pedidos pendentes em modo incremental, sem estourar o orçamento."""
    while budget > 0:
        pending = lock.take_pending(state_dir)
        if pending is None:
            break
        _index_once(cfg, False, False, None, True, False,
                    pending if pending in VALID_SOURCES else "cli")
        budget -= 1
    return budget


def _index_once(
    cfg: Config,
    full: bool = False,
    dry_run: bool = False,
    progress: Callable[[int, str], None] | None = None,
    embed: bool = True,
    embed_only: bool = False,
    source: str = "cli",
) -> IndexReport:
    gate = SecurityGate(
        cfg.root,
        policy=cfg.security.policy,
        scan_content=cfg.security.scan_content,
        min_entropy=cfg.security.min_entropy,
        extra_exclude=cfg.index.exclude,
        extra_include=cfg.index.include,
    )
    opts = ChunkOptions(max_tokens=cfg.chunk.max_tokens, min_tokens=cfg.chunk.min_tokens)
    report = IndexReport()
    started = time.perf_counter()
    skip_reasons: dict[str, int] = {}

    with open_db(cfg.db_path) as conn:
        docs = DocumentRepo(conn)
        chunks = ChunkRepo(conn)
        events = SecurityEventRepo(conn)
        runs = RunRepo(conn)

        known = docs.fingerprints()
        seen_paths: set[str] = set()
        mode = "embed-only" if embed_only else ("full" if full else "incremental")
        run_id = None if dry_run else runs.start(mode, source, gitinfo.read_state(cfg.root))
        batch = 0

        try:
            if embed_only:
                er = embed_pending(cfg, conn)
                report.embed_error = er.error
                report.stats = _bump(report.stats, embedded=er.embedded)
                conn.commit()
                raise _EmbedOnlyDoneError

            fingerprints = (
                None if full
                else {p: (size, mtime) for p, (_h, size, mtime, cv) in known.items()
                      if cv == CHUNKER_VERSION}
            )
            for walked in _all_sources(cfg, gate, fingerprints):
                report.stats = _bump(report.stats, files_seen=1)
                if progress:
                    progress(report.stats.files_seen, walked.rel_path)

                if walked.unchanged:
                    seen_paths.add(walked.rel_path)
                    report.stats = _bump(report.stats, unchanged=1)
                    continue

                d = walked.decision
                if d.verdict is Verdict.SKIP:
                    reason = d.rule_id or "ignore"
                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                    report.stats = _bump(report.stats, skipped=1)
                    continue

                if d.verdict is Verdict.BLOCK:
                    report.stats = _bump(report.stats, blocked=1)
                    report.blocked_paths.append(walked.rel_path)
                    if not dry_run:
                        # Arquivo que virou sensível some do índice.
                        docs.delete_many([walked.rel_path])
                        events.clear_for(walked.rel_path)
                        events.record(run_id, d.findings)
                        batch += 1
                    continue

                seen_paths.add(walked.rel_path)
                text = d.content or ""
                chash = content_hash(text)
                prior = known.get(walked.rel_path)

                if (
                    not full
                    and prior
                    and prior[0] == chash
                    and prior[3] == CHUNKER_VERSION
                ):
                    report.stats = _bump(report.stats, unchanged=1)
                    continue

                parsed = parsers.parse(
                    walked.rel_path, text, include_unknown=cfg.index.include_unknown
                )
                if parsed is None:
                    skip_reasons["unsupported"] = skip_reasons.get("unsupported", 0) + 1
                    report.stats = _bump(report.stats, skipped=1)
                    seen_paths.discard(walked.rel_path)
                    continue
                if parsed.degraded:
                    report.degraded += 1

                produced = chunk_document(walked.rel_path, text, parsed, opts)
                report.stats = _bump(report.stats, indexed=1, chunks=len(produced))
                report.new_chunks += len(produced)
                if prior:
                    report.modified_documents += 1
                else:
                    report.new_documents += 1
                if d.verdict is Verdict.ALLOW_REDACTED:
                    report.stats = _bump(report.stats, redacted=1)

                if dry_run:
                    continue

                doc = Document(
                    id=document_id(walked.rel_path),
                    rel_path=walked.rel_path,
                    doc_kind=parsed.doc_kind,
                    size_bytes=walked.size_bytes,
                    mtime_ns=walked.mtime_ns,
                    content_hash=chash,
                    chunker_version=CHUNKER_VERSION,
                    lang=parsed.lang,
                    title=parsed.title,
                    redacted=d.verdict is Verdict.ALLOW_REDACTED,
                )
                docs.upsert(doc)
                chunks.replace_for_document(doc.id, produced)
                events.clear_for(walked.rel_path)
                events.record(run_id, d.findings)

                batch += 1
                if batch >= cfg.index.batch_size:
                    conn.commit()
                    batch = 0

            # Documentos que sumiram do disco.
            gone = [p for p in known if p not in seen_paths and p not in report.blocked_paths]
            if gone and not dry_run:
                docs.delete_many(gone)
            report.stats = _bump(report.stats, removed=len(gone))

            if not dry_run:
                conn.commit()

            # Embedder fora do ar NÃO derruba a indexação: os chunks já estão
            # gravados e `ragx index --embed-only` completa depois (ADR-0004).
            if embed and not dry_run:
                er = embed_pending(cfg, conn)
                report.embed_error = er.error
                report.stats = _bump(report.stats, embedded=er.embedded)
                conn.commit()

        except _EmbedOnlyDoneError:
            pass
        except KeyboardInterrupt:
            report.interrupted = True
            if not dry_run:
                conn.commit()  # preserva os lotes já processados
            raise
        finally:
            elapsed = int((time.perf_counter() - started) * 1000)
            report.stats = _bump(report.stats, duration_ms=elapsed)
            object.__setattr__(report.stats, "skip_reasons", skip_reasons)
            if not dry_run and run_id is not None:
                runs.finish(
                    run_id,
                    {
                        "files_seen": report.stats.files_seen,
                        "indexed": report.stats.indexed,
                        "skipped": report.stats.skipped,
                        "blocked": report.stats.blocked,
                        "removed": report.stats.removed,
                        "chunks": chunks.count(),
                        "embedded": report.stats.embedded,
                        "duration_ms": elapsed,
                    },
                    error="interrupted" if report.interrupted else None,
                )
                set_meta(conn, "chunker_version", CHUNKER_VERSION)
                conn.commit()

    return report


def _all_sources(
    cfg: Config, gate: SecurityGate, fingerprints: dict[str, tuple[int, int]] | None
) -> Iterator[WalkedFile]:
    """O projeto e, depois, o conhecimento base.

    Uma única cadeia de geradores: o corpo do laço de indexação não sabe (nem
    precisa saber) de onde o arquivo veio. Cada fonte base tem o SEU gate,
    enraizado nela — regra de nome e .gitignore avaliam o caminho real, e o
    prefixo `@base/<fonte>/` só aparece do lado de fora.
    """
    yield from iter_files(
        cfg.root, gate,
        max_bytes=cfg.index.max_file_bytes,
        follow_symlinks=cfg.index.follow_symlinks,
        fingerprints=fingerprints,
    )
    if not cfg.base.enabled:
        return
    for name, path in base_source.active_roots(cfg):
        yield from iter_files(
            path,
            SecurityGate(
                path,
                policy=cfg.security.policy,
                scan_content=cfg.security.scan_content,
                min_entropy=cfg.security.min_entropy,
            ),
            # Conteúdo de terceiro entra com orçamento próprio, menor.
            max_bytes=cfg.base.max_file_bytes,
            follow_symlinks=False,
            fingerprints=fingerprints,
            prefix=f"{base_source.PREFIX}/{name}/",
        )


def _bump(s: IndexStats, **kw: int) -> IndexStats:
    data = {
        "files_seen": s.files_seen, "indexed": s.indexed, "unchanged": s.unchanged,
        "skipped": s.skipped, "blocked": s.blocked, "redacted": s.redacted,
        "removed": s.removed, "chunks": s.chunks, "embedded": s.embedded,
        "duration_ms": s.duration_ms, "skip_reasons": s.skip_reasons,
    }
    for k, v in kw.items():
        if k == "duration_ms":
            data[k] = v
        else:
            data[k] = data[k] + v  # type: ignore[operator]
    return IndexStats(**data)  # type: ignore[arg-type]


def walk_preview(cfg: Config) -> Iterator[WalkedFile]:
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    yield from iter_files(cfg.root, gate, max_bytes=cfg.index.max_file_bytes)


def status(cfg: Config) -> dict[str, object]:
    if not Path(cfg.db_path).exists():
        return {"initialized": False}
    with open_db(cfg.db_path) as conn:
        docs = DocumentRepo(conn)
        chunks = ChunkRepo(conn)
        runs = RunRepo(conn)
        by_lang = {
            r["lang"]: r["n"]
            for r in conn.execute(
                "SELECT lang, COUNT(*) n FROM documents GROUP BY lang ORDER BY n DESC"
            )
        }
        events = conn.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
        embeddings = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        model = conn.execute(
            "SELECT id, dim, versioned_dim FROM embedding_models ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return {
            "initialized": True,
            "documents": docs.count(),
            "chunks": chunks.count(),
            "by_lang": by_lang,
            "security_events": events,
            "embeddings": embeddings,
            "embedding_model": dict(model) if model else None,
            "last_run": runs.latest(),
        }

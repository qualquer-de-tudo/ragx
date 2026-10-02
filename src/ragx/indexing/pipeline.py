"""Pipeline de indexação incremental.

walker -> gate -> parser -> chunker -> store

Transação por LOTE (não uma gigante): Ctrl+C deixa o banco consistente com os
lotes já confirmados. Ver docs/04-indexacao.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ragx import gitinfo
from ragx.base import source as base_source
from ragx.config import Config
from ragx.core.errors import IndexBusyError, UsageError
from ragx.core.ids import CHUNKER_VERSION, content_hash, document_id
from ragx.core.models import Document, IndexStats, Verdict
from ragx.indexing import freshness, lock, parsers, status_file
from ragx.indexing.chunkers import ChunkOptions, chunk_document
from ragx.indexing.context import ensure_context
from ragx.indexing.embed import embed_pending
from ragx.indexing.parallel import ParallelStats, Prepared, WorkerSpec, process_stream, resolve_jobs
from ragx.indexing.verdicts import BLOCKED, CACHED_SKIPS
from ragx.indexing.verdicts import prepare as vprepare
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db, set_meta
from ragx.storage.repositories import (
    ChunkRepo,
    DocumentRepo,
    RunRepo,
    SecurityEventRepo,
    VerdictRepo,
)
from ragx.walk import WalkedFile, iter_candidates, iter_files, iter_paths, normalizar_caminho

VALID_SOURCES = frozenset({
    "cli", "panel", "watch", "sync", "mcp:refresh", "mcp:index",
    "hook:post-checkout", "hook:post-commit", "hook:post-merge", "paths", "touch", "mcp:touch",
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
    #: arquivos que existem mas não deram para ler agora; ficam como estavam no índice
    unreadable: int = 0
    #: chunks de documentos modificados que sobreviveram à edição (mesmo id) e os que saíram
    chunks_kept: int = 0
    chunks_removed: int = 0
    #: vetores int8 importados de `knowledge/embeddings` e os que seguem só grosseiros (RAGX-0144)
    imported_embeddings: int = 0
    coarse_only: int = 0
    embed_warning: str | None = None
    #: workers do pool do primeiro índice (RAGX-0152); 0 = sequencial (abaixo do limiar, `jobs = 1`, dry-run)
    parallel_jobs: int = 0
    #: motivo, quando o pool caiu no meio e o resto da rodada rodou no processo principal
    parallel_fallback: str | None = None
    #: caminhos de documentos indexados, alterados, bloqueados ou removidos na rodada (RAGX-0151):
    #: é o que o grafo incremental precisa para atualizar só o que mudou
    touched_documents: list[str] = field(default_factory=list)


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
    on_event: Callable[[dict[str, Any]], None] | None = None,
    upgrade_coarse: bool | None = None,
) -> IndexReport:
    """`upgrade_coarse`: completar o float32 de vetores só grosseiros (os importados de `knowledge/`).

    `None` (padrão): só quando a pessoa pede (`--embed-only`) ou roda `ragx index` / o painel. Hooks,
    `watch`, `touch` e o `refresh` do agente NÃO o fazem: reembutir milhares de chunks em segundo
    plano, depois de um `ragx sync` que os deixou de propósito grosseiros, seria uma surpresa.
    """
    if source not in VALID_SOURCES:
        raise UsageError(f"origem desconhecida: {source}")
    if upgrade_coarse is None:
        upgrade_coarse = embed_only or source in ("cli", "panel")
    if dry_run:
        return _index_once(cfg, full, dry_run, progress, embed, embed_only, source, on_event, upgrade_coarse)

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
                status_file.write_status(cfg)
                raise IndexBusyError(current)
            break
        time.sleep(0.5)

    status_file.write_status(cfg)  # depois do while da trava: mostra "running"
    budget = MAX_PENDING_RERUNS
    try:
        report = _index_once(
            cfg, full, dry_run, progress, embed, embed_only, source, on_event, upgrade_coarse
        )
        budget = _drain_pending(cfg, state_dir, budget, report)
    finally:
        lock.release(state_dir)
        status_file.write_status(cfg)  # estado final, running = null

    # Só chega aqui em caminho de sucesso: Ctrl+C ou erro dentro do `try`
    # acima já teria propagado no `finally`, sem passar por esta linha. Sem
    # essa separação, reexecutar a indexação ao desenrolar uma exceção de
    # verdade engoliria KeyboardInterrupt e trocaria o erro original por uma
    # falha da rodada extra.
    #
    # Um pedido pode ter chegado entre o último take_pending acima e o
    # release: reobtém a trava e drena de novo enquanto houver pedido
    # pendente e orçamento — não só uma vez, senão a mesma corrida reaparece
    # uma rodada depois. O orçamento é o mesmo da primeira drenagem, nunca
    # reinicia.
    while budget > 0 and lock.is_pending(state_dir) and lock.try_acquire(state_dir, "index", source):
        try:
            budget = _drain_pending(cfg, state_dir, budget, report)
        finally:
            lock.release(state_dir)
            status_file.write_status(cfg)

    return report


# Arquivos que mudam O QUE é visitado: mexer neles invalida a reindexação por caminho.
_ARQUIVOS_DE_REGRA = frozenset({".gitignore", ".dockerignore", ".ragignore", "ragx.toml"})


def index_paths(
    cfg: Config,
    paths: Sequence[str],
    *,
    embed: bool = True,
    source: str = "paths",
    wait_s: float = 0.0,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    gate: SecurityGate | None = None,
) -> IndexReport:
    """Reindexa SÓ os arquivos pedidos: sem varrer a árvore e sem chamar o git.

    `gate` (RAGX-0147): o watcher passa o dele, que já existe, em vez de construir outro a cada lote.

    É o que uma edição feita no meio de uma sessão precisa (RAGX-0140): o custo do arquivo, e
    não o do projeto. O Security Gate é o mesmo e roda antes de qualquer byte (`iter_paths`
    delega ao mesmo `_examinar` da varredura); o que se dispensa é a enumeração e o git, e as
    recusas da varredura (caminho absoluto, `..`, pasta podada, link para fora) são repetidas.

    Cai no `index_project` incremental completo quando o pedido não cabe no atalho: mais de
    `watch.max_batch` caminhos, ou um arquivo de regra (`.gitignore`, `.dockerignore`,
    `.ragignore`, `ragx.toml`), que muda o que é visitado.
    """
    if source not in VALID_SOURCES:
        raise UsageError(f"origem desconhecida: {source}")
    vistos: dict[str, None] = {}
    for bruto in paths:
        rel = normalizar_caminho(bruto)
        if rel is not None:
            vistos[rel] = None
    rels = list(vistos)
    if not rels:
        return IndexReport()
    if len(rels) > cfg.watch.max_batch or any(r.rsplit("/", 1)[-1] in _ARQUIVOS_DE_REGRA for r in rels):
        return index_project(cfg, source=source, embed=embed, wait_s=wait_s, on_event=on_event)

    state_dir = cfg.state_dir
    deadline = time.monotonic() + max(wait_s, 0.0)
    while not lock.try_acquire(state_dir, "index", source):
        if time.monotonic() >= deadline:
            current = lock.holder(state_dir)
            lock.mark_pending(state_dir, source)
            if not lock.try_acquire(state_dir, "index", source):
                raise IndexBusyError(current)
            break
        time.sleep(0.5)

    budget = MAX_PENDING_RERUNS
    try:
        report = _index_paths_once(cfg, rels, embed, source, on_event, gate)
        budget = _drain_pending(cfg, state_dir, budget, report)
    finally:
        lock.release(state_dir)
        # uma vez, no fim, sem perguntar os hooks ao git (uma edição não os muda)
        status_file.write_status(cfg, probe_hooks=False)
    return report


def _index_paths_once(
    cfg: Config,
    rels: list[str],
    embed: bool,
    source: str,
    on_event: Callable[[dict[str, Any]], None] | None,
    gate: SecurityGate | None = None,
) -> IndexReport:
    if gate is None:
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

        pedidos = set(rels)
        ensure_context(conn)  # prefixo de contexto e vetores em dia com a versão (RAGX-0166)
        known = {p: v for p, v in docs.fingerprints().items() if p in pedidos}
        seen_paths: set[str] = set()
        # branch e commit vêm da última run COMPLETA, sem chamar o git; `dirty = 1` porque
        # indexar por caminho é, por definição, olhar arquivos que mudaram depois dela.
        ultima = conn.execute(
            "SELECT git_branch, git_commit FROM index_runs WHERE finished_at IS NOT NULL "
            "AND mode NOT IN ('embed-only', 'paths') AND error IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        git = (
            gitinfo.GitState(branch=ultima[0], commit=ultima[1], dirty=True)
            if ultima is not None and ultima[1] else None
        )
        run_id = runs.start("paths", source, git)
        run_error: str | None = None
        verdicts = vprepare(conn, cfg, full=False, dry_run=False, only=pedidos)
        ctx = _Ctx(
            cfg=cfg, conn=conn, opts=opts, report=report, skip_reasons=skip_reasons,
            docs=docs, chunks=chunks, events=events, run_id=run_id, known=known,
            seen_paths=seen_paths, full=False, dry_run=False, on_event=on_event,
            verdicts=verdicts, vrepo=VerdictRepo(conn),
        )
        try:
            fingerprints = {
                p: (size, mtime) for p, (_h, size, mtime, cv) in known.items() if cv == CHUNKER_VERSION
            }
            for walked in iter_paths(
                cfg.root, gate, rels, max_bytes=cfg.index.max_file_bytes,
                follow_symlinks=cfg.index.follow_symlinks, fingerprints=fingerprints,
                verdicts=verdicts,
            ):
                report.stats = _bump(report.stats, files_seen=1)
                _handle(ctx, walked)

            # Pedidos que sumiram do disco (ou que a varredura também não alcançaria).
            gone = [p for p in known if p not in seen_paths and p not in report.blocked_paths]
            if gone:
                docs.delete_many(gone)
                report.touched_documents.extend(gone)
            report.stats = _bump(report.stats, removed=len(gone))
            _flush_verdicts(ctx, gone=[p for p in ctx.verdicts if p not in ctx.walked])
            conn.commit()

            if embed:
                er = embed_pending(cfg, conn, progress=_embed_cb(on_event), upgrade_coarse=False)
                report.embed_error = er.error
                report.imported_embeddings += er.imported
                report.coarse_only = er.coarse_only
                report.embed_warning = er.import_warning or report.embed_warning
                report.stats = _bump(report.stats, embedded=er.embedded)
                conn.commit()
        except KeyboardInterrupt:
            report.interrupted = True
            run_error = "interrupted"
            conn.commit()
            raise
        except Exception as exc:
            run_error = str(exc)
            raise
        finally:
            elapsed = int((time.perf_counter() - started) * 1000)
            report.stats = _bump(report.stats, duration_ms=elapsed)
            object.__setattr__(report.stats, "skip_reasons", skip_reasons)
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
                error=run_error,
            )
            set_meta(conn, "chunker_version", CHUNKER_VERSION)
            conn.commit()
    return report


def _drain_pending(
    cfg: Config, state_dir: Path, budget: int, report: IndexReport | None = None
) -> int:
    """Roda pedidos pendentes em modo incremental, sem estourar o orçamento.

    Os documentos tocados nas rodadas extras entram em `report.touched_documents` (RAGX-0151).
    """
    while budget > 0:
        pending = lock.take_pending(state_dir)
        if pending is None:
            break
        extra = _index_once(cfg, False, False, None, True, False,
                            pending if pending in VALID_SOURCES else "cli", None)
        if report is not None:
            report.touched_documents.extend(p for p in extra.touched_documents if p not in report.touched_documents)
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
    on_event: Callable[[dict[str, Any]], None] | None = None,
    upgrade_coarse: bool = True,
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

        if not dry_run:
            ensure_context(conn)  # prefixo de contexto e vetores em dia com a versão (RAGX-0166)
        known = docs.fingerprints()
        seen_paths: set[str] = set()
        unreadable_dirs: set[str] = set()
        mode = "embed-only" if embed_only else ("full" if full else "incremental")
        run_id = None if dry_run else runs.start(mode, source, gitinfo.read_state(cfg.root))
        run_error: str | None = None
        fonte: Iterator[tuple[WalkedFile, Prepared | None]] | None = None

        try:
            if embed_only:
                er = embed_pending(cfg, conn, progress=_embed_cb(on_event), upgrade_coarse=upgrade_coarse)
                report.embed_error = er.error
                report.imported_embeddings += er.imported
                report.coarse_only = er.coarse_only
                report.embed_warning = er.import_warning or report.embed_warning
                report.stats = _bump(report.stats, embedded=er.embedded)
                conn.commit()
                raise _EmbedOnlyDoneError

            fingerprints = (
                None if full
                else {p: (size, mtime) for p, (_h, size, mtime, cv) in known.items()
                      if cv == CHUNKER_VERSION}
            )
            verdicts = vprepare(conn, cfg, full=full, dry_run=dry_run)
            ctx = _Ctx(
                cfg=cfg, conn=conn, opts=opts, report=report, skip_reasons=skip_reasons,
                docs=docs, chunks=chunks, events=events, run_id=run_id, known=known,
                seen_paths=seen_paths, full=full, dry_run=dry_run, on_event=on_event,
                verdicts=verdicts, vrepo=VerdictRepo(conn),
            )
            jobs = 1 if dry_run else resolve_jobs(cfg.index.jobs)
            stats_paralelo = ParallelStats()
            fonte = _all_sources(
                cfg, gate, fingerprints, unreadable_dirs, verdicts, jobs=jobs, stats=stats_paralelo
            )
            for walked, pre in fonte:
                report.stats = _bump(report.stats, files_seen=1)
                if on_event:
                    on_event({"phase": "scan", "done": report.stats.files_seen, "total": None})
                if progress:
                    progress(report.stats.files_seen, walked.rel_path)

                _handle(ctx, walked, pre)
            report.parallel_jobs = stats_paralelo.jobs
            report.parallel_fallback = stats_paralelo.fell_back

            # Documentos que sumiram do disco.
            gone = [
                p for p in known
                if p not in seen_paths
                and p not in report.blocked_paths
                and not _sob_pasta_ilegivel(p, unreadable_dirs)
            ]
            if gone and not dry_run:
                docs.delete_many(gone)
                report.touched_documents.extend(gone)
            report.stats = _bump(report.stats, removed=len(gone))
            # veredito de arquivo que sumiu (fora de pasta ilegível: lá não se sabe)
            _flush_verdicts(ctx, gone=[
                p for p in ctx.verdicts
                if p not in ctx.walked and not _sob_pasta_ilegivel(p, unreadable_dirs)
            ])

            if not dry_run:
                conn.commit()

            # Embedder fora do ar NÃO derruba a indexação: os chunks já estão
            # gravados e `ragx index --embed-only` completa depois (ADR-0004).
            if embed and not dry_run:
                er = embed_pending(cfg, conn, progress=_embed_cb(on_event), upgrade_coarse=upgrade_coarse)
                report.embed_error = er.error
                report.imported_embeddings += er.imported
                report.coarse_only = er.coarse_only
                report.embed_warning = er.import_warning or report.embed_warning
                report.stats = _bump(report.stats, embedded=er.embedded)
                conn.commit()

        except _EmbedOnlyDoneError:
            pass
        except KeyboardInterrupt:
            report.interrupted = True
            run_error = "interrupted"
            if not dry_run:
                conn.commit()  # preserva os lotes já processados
            raise
        except Exception as exc:
            # Sem isto, qualquer exceção real (não Ctrl+C) gravava a corrida
            # como limpa (`error=None`) — e a rodada seguinte de `freshness`/
            # `status.json` a escolhia como "última indexação útil", relatando
            # a árvore como em dia mesmo depois de uma corrida que quebrou no
            # meio. A exceção continua propagando: isto só registra o erro.
            run_error = str(exc)
            raise
        finally:
            # Ctrl+C ou erro no meio da varredura: fecha o gerador AGORA, o que desliga o pool de processos
            # (cancela o que não começou e espera só os lotes em voo) antes de a exceção sair daqui.
            if fonte is not None:
                fonte.close()  # type: ignore[attr-defined]
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
                    error=run_error,
                )
                set_meta(conn, "chunker_version", CHUNKER_VERSION)
                conn.commit()

    return report


@dataclass
class _Ctx:
    """O que o tratamento de UM arquivo precisa, para a varredura e para a reindexação por caminho."""

    cfg: Config
    conn: Any
    opts: ChunkOptions
    report: IndexReport
    skip_reasons: dict[str, int]
    docs: DocumentRepo
    chunks: ChunkRepo
    events: SecurityEventRepo
    run_id: int | None
    known: dict[str, Any]
    seen_paths: set[str]
    full: bool
    dry_run: bool
    on_event: Callable[[dict[str, Any]], None] | None = None
    batch: int = 0
    #: veredito guardado (RAGX-0139): o que a rodada pode usar, e o que ela decidiu de novo
    verdicts: dict[str, tuple[int, int, str, str | None]] = field(default_factory=dict)
    vrepo: VerdictRepo | None = None
    vput: dict[str, tuple[str, str | None, int, int]] = field(default_factory=dict)
    vdrop: set[str] = field(default_factory=set)
    walked: set[str] = field(default_factory=set)


def _guardar(ctx: _Ctx, walked: WalkedFile, veredito: str, rule_id: str | None) -> None:
    """Enfileira o veredito de um arquivo que fica FORA do índice (gravado em `_flush_verdicts`)."""
    if ctx.dry_run or ctx.vrepo is None or walked.mtime_ns == 0:
        return
    ctx.vput[walked.rel_path] = (veredito, rule_id, walked.size_bytes, walked.mtime_ns)
    ctx.vdrop.discard(walked.rel_path)


def _sem_veredito(ctx: _Ctx, rel: str) -> None:
    """O arquivo não é mais um caso de cache (virou documento, ou outra razão de pular)."""
    if not ctx.dry_run and ctx.vrepo is not None and rel in ctx.verdicts:
        ctx.vdrop.add(rel)
        ctx.vput.pop(rel, None)


def _flush_verdicts(ctx: _Ctx, gone: Iterable[str] = ()) -> None:
    """Grava (na mesma transação do índice) os vereditos novos e apaga os que caducaram."""
    if ctx.dry_run or ctx.vrepo is None:
        return
    apagar = ctx.vdrop | set(gone)
    if apagar:
        ctx.vrepo.delete_many(apagar)
    if ctx.vput:
        ctx.vrepo.put_many((p, v, r, size, mtime) for p, (v, r, size, mtime) in ctx.vput.items())
    ctx.vdrop.clear()
    ctx.vput.clear()


def _handle(ctx: _Ctx, walked: WalkedFile, pre: Prepared | None = None) -> None:
    """Trata UM arquivo entregue pelo walker: BLOCK, parse, chunk, upsert, eventos.

    `pre` (RAGX-0152): hash, parse e chunking que um worker do pool já fez sobre o texto admitido pelo Gate; sem
    ele, tudo é feito aqui. A escrita no banco é a mesma nos dois casos.
    """
    cfg, report, skip_reasons = ctx.cfg, ctx.report, ctx.skip_reasons
    docs, chunks, events = ctx.docs, ctx.chunks, ctx.events
    known, seen_paths = ctx.known, ctx.seen_paths
    full, dry_run, run_id, opts, on_event = ctx.full, ctx.dry_run, ctx.run_id, ctx.opts, ctx.on_event
    ctx.walked.add(walked.rel_path)
    if walked.unchanged:
        seen_paths.add(walked.rel_path)
        report.stats = _bump(report.stats, unchanged=1)
        _sem_veredito(ctx, walked.rel_path)
        return

    if walked.unreadable:
        # Existe, mas está travado agora (antivírus, editor logo após
        # o save). Não é "removido": nada é regravado e o documento,
        # os chunks e os vetores ficam como estavam (RAGX-0133).
        seen_paths.add(walked.rel_path)
        report.unreadable += 1
        skip_reasons["unreadable"] = skip_reasons.get("unreadable", 0) + 1
        report.stats = _bump(report.stats, skipped=1)
        return

    d = walked.decision
    if d.verdict is Verdict.SKIP:
        reason = d.rule_id or "ignore"
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        report.stats = _bump(report.stats, skipped=1)
        if not walked.cached_verdict:
            if reason in CACHED_SKIPS:  # binário, indecodável: decidido lendo o arquivo
                _guardar(ctx, walked, reason, reason)
            else:
                _sem_veredito(ctx, walked.rel_path)
        return

    if d.verdict is Verdict.BLOCK:
        report.stats = _bump(report.stats, blocked=1)
        report.blocked_paths.append(walked.rel_path)
        if not dry_run:
            # Arquivo que virou sensível some do índice.
            docs.delete_many([walked.rel_path])
            report.touched_documents.append(walked.rel_path)
            if not walked.cached_verdict:
                events.clear_for(walked.rel_path)
                events.record(run_id, d.findings)
                _guardar(ctx, walked, BLOCKED, d.rule_id)
            # veredito guardado: os `security_events` da decisão original continuam como estão
            ctx.batch += 1
        return

    seen_paths.add(walked.rel_path)
    text = d.content or ""
    chash = pre.chash if pre is not None else content_hash(text)
    prior = known.get(walked.rel_path)

    if (
        not full
        and prior
        and prior[0] == chash
        and prior[3] == CHUNKER_VERSION
    ):
        report.stats = _bump(report.stats, unchanged=1)
        _sem_veredito(ctx, walked.rel_path)
        return

    if pre is None:
        parsed = parsers.parse(
            walked.rel_path, text, include_unknown=cfg.index.include_unknown
        )
        pre = (
            None if parsed is None
            else Prepared(
                supported=True, chash=chash, doc_kind=parsed.doc_kind, lang=parsed.lang,
                title=parsed.title, degraded=parsed.degraded,
                chunks=tuple(chunk_document(walked.rel_path, text, parsed, opts)),
            )
        )
    if pre is None or not pre.supported:
        skip_reasons["unsupported"] = skip_reasons.get("unsupported", 0) + 1
        report.stats = _bump(report.stats, skipped=1)
        seen_paths.discard(walked.rel_path)
        _guardar(ctx, walked, "unsupported", "unsupported")
        return
    _sem_veredito(ctx, walked.rel_path)
    if pre.degraded:
        report.degraded += 1

    produced = list(pre.chunks)
    report.stats = _bump(report.stats, indexed=1, chunks=len(produced))
    if on_event:
        on_event({"phase": "chunk", "done": report.stats.indexed, "total": None})
    report.new_chunks += len(produced)
    if prior:
        report.modified_documents += 1
    else:
        report.new_documents += 1
    if d.verdict is Verdict.ALLOW_REDACTED:
        report.stats = _bump(report.stats, redacted=1)

    if dry_run:
        return

    doc = Document(
        id=document_id(walked.rel_path),
        rel_path=walked.rel_path,
        doc_kind=pre.doc_kind,  # type: ignore[arg-type]
        size_bytes=walked.size_bytes,
        mtime_ns=walked.mtime_ns,
        content_hash=chash,
        chunker_version=CHUNKER_VERSION,
        lang=pre.lang,
        title=pre.title,
        redacted=d.verdict is Verdict.ALLOW_REDACTED,
    )
    docs.upsert(doc)
    report.touched_documents.append(walked.rel_path)
    trocou = chunks.replace_for_document(doc.id, produced)
    report.chunks_kept += trocou.kept
    report.chunks_removed += trocou.removed
    events.clear_for(walked.rel_path)
    events.record(run_id, d.findings)

    ctx.batch += 1
    if ctx.batch >= cfg.index.batch_size:
        _flush_verdicts(ctx)
        ctx.conn.commit()
        ctx.batch = 0


def _sob_pasta_ilegivel(rel_path: str, pastas: set[str]) -> bool:
    """O caminho é uma das pastas que não abriram, ou está sob uma delas."""
    return any(p == "" or rel_path == p or rel_path.startswith(p + "/") for p in pastas)


def _worker_spec(cfg: Config) -> WorkerSpec:
    return WorkerSpec(
        root=str(cfg.root),
        policy=str(cfg.security.policy),
        scan_content=cfg.security.scan_content,
        min_entropy=cfg.security.min_entropy,
        extra_exclude=tuple(cfg.index.exclude),
        extra_include=tuple(cfg.index.include),
        max_tokens=cfg.chunk.max_tokens,
        min_tokens=cfg.chunk.min_tokens,
        include_unknown=cfg.index.include_unknown,
    )


def _all_sources(
    cfg: Config,
    gate: SecurityGate,
    fingerprints: dict[str, tuple[int, int]] | None,
    unreadable_dirs: set[str] | None = None,
    verdicts: dict[str, tuple[int, int, str, str | None]] | None = None,
    jobs: int = 1,
    stats: ParallelStats | None = None,
) -> Iterator[tuple[WalkedFile, Prepared | None]]:
    """O projeto e, depois, o conhecimento base.

    Uma única cadeia de geradores: o corpo do laço de indexação não sabe (nem
    precisa saber) de onde o arquivo veio. Cada fonte base tem o SEU gate,
    enraizado nela — regra de nome e .gitignore avaliam o caminho real, e o
    prefixo `@base/<fonte>/` só aparece do lado de fora.

    O projeto passa por `process_stream` (RAGX-0152): com `jobs > 1` e candidatos suficientes, leitura, Gate,
    parse e chunking rodam num pool de processos e voltam na ordem da varredura (o segundo item da tupla é o
    resultado do parse; `None` no caminho sequencial). O conhecimento base continua sequencial.
    """
    yield from process_stream(
        iter_candidates(
            cfg.root, gate,
            max_bytes=cfg.index.max_file_bytes,
            follow_symlinks=cfg.index.follow_symlinks,
            fingerprints=fingerprints,
            unreadable_dirs=unreadable_dirs,
            verdicts=verdicts,
        ),
        gate, _worker_spec(cfg), jobs, stats,
    )
    if not cfg.base.enabled:
        return
    for name, path in base_source.active_roots(cfg):
        for walked in iter_files(
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
            unreadable_dirs=unreadable_dirs,
            verdicts=verdicts,
            prefix=f"{base_source.PREFIX}/{name}/",
        ):
            yield walked, None


def _embed_cb(
    on_event: Callable[[dict[str, Any]], None] | None,
) -> Callable[[int, int], None] | None:
    if on_event is None:
        return None
    return lambda done, total: on_event({"phase": "embed", "done": done, "total": total})


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
        last_done = conn.execute(
            "SELECT * FROM index_runs WHERE finished_at IS NOT NULL "
            "AND mode NOT IN ('embed-only', 'paths') AND error IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        fresh = freshness.compute(cfg, conn, dict(last_done) if last_done else None)
        return {
            "initialized": True,
            "documents": docs.count(),
            "chunks": chunks.count(),
            "by_lang": by_lang,
            "security_events": events,
            "embeddings": embeddings,
            "embedding_model": dict(model) if model else None,
            "last_run": runs.latest(),
            "freshness": fresh,
            "recent_runs": runs.recent(10),
        }

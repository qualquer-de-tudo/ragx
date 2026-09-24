"""`ragx sync` — reconstrói o índice local a partir do conhecimento versionado.

    git pull && ragx sync

Detecção de delta em duas vias (docs/12-git-sync.md):
  1. Git — `git diff --name-status <ultimo_sync> HEAD`, rápido e exato
  2. Fallback por `content_hash`, quando não há Git ou o commit sumiu
     (rebase, shallow clone). Cai sozinho, sem falhar.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from ragx.config import Config
from ragx.indexing.pipeline import index_project
from ragx.procs import run_quiet
from ragx.storage.db import get_meta, open_db, set_meta
from ragx.sync import serialize
from ragx.sync.rehydrate import RehydrateReport, rehydrate


@dataclass
class SyncReport:
    mode: str = "hash"  # git | hash
    from_commit: str | None = None
    to_commit: str | None = None
    changed: list[str] = field(default_factory=list)
    rehydrate: RehydrateReport = field(default_factory=RehydrateReport)
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    chunks: int = 0
    embedded: int = 0
    entities: int = 0
    relations: int = 0
    serialized: serialize.SerializeReport | None = None
    tasks: object | None = None  # TaskSyncReport
    duration_ms: int = 0
    warnings: list[str] = field(default_factory=list)


def _git(root: Path, *args: str) -> str | None:
    try:
        out = run_quiet(
            ["git", *args], cwd=root, capture_output=True, text=True,
            check=True, timeout=15,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def detect_delta(cfg: Config, from_commit: str | None = None) -> tuple[str, list[str], str | None, str | None]:
    """Devolve (modo, arquivos_alterados, from, to)."""
    head = _git(cfg.root, "rev-parse", "HEAD")
    if head is None:
        return "hash", [], None, None

    with open_db(cfg.db_path, read_only=True) as conn:
        last = from_commit or get_meta(conn, "last_sync_commit")

    if not last:
        return "hash", [], None, head
    # Commit reescrito (rebase) ou ausente (shallow): cai no fallback sozinho.
    if _git(cfg.root, "cat-file", "-e", f"{last}^{{commit}}") is None:
        return "hash", [], last, head

    diff = _git(cfg.root, "diff", "--name-only", f"{last}", "HEAD")
    if diff is None:
        return "hash", [], last, head
    changed = [line.strip() for line in diff.splitlines() if line.strip()]
    return "git", changed, last, head


def sync(
    cfg: Config,
    from_commit: str | None = None,
    full: bool = False,
    out_dir: str = "knowledge",
    write_knowledge: bool = True,
) -> SyncReport:
    report = SyncReport()
    t0 = time.perf_counter()

    report.mode, report.changed, report.from_commit, report.to_commit = detect_delta(
        cfg, from_commit
    )

    # [1] Reidrata o que já está versionado — antes do delta.
    if serialize.read_manifest(cfg, out_dir) is not None:
        _hydrated, report.rehydrate = rehydrate(cfg, out_dir)
        if report.rehydrate.missing:
            report.warnings.append(
                f"{report.rehydrate.missing} chunk(s) apontam para arquivos que não "
                "existem mais — knowledge/ está à frente do working tree"
            )
        if report.rehydrate.blocked:
            report.warnings.append(
                f"{report.rehydrate.blocked} chunk(s) vieram de arquivos que agora "
                "são bloqueados pelo gate; serão removidos do índice"
            )

    # [2] Aplica o delta reindexando (incremental por content_hash).
    indexed = index_project(cfg, full=full, source="sync", wait_s=30)
    report.indexed = indexed.stats.indexed
    report.unchanged = indexed.stats.unchanged
    report.removed = indexed.stats.removed
    report.chunks = indexed.new_chunks
    report.embedded = indexed.stats.embedded
    if indexed.embed_error:
        report.warnings.append(f"embeddings incompletos: {indexed.embed_error.splitlines()[0]}")

    # [3] Regrava os artefatos versionados.
    if write_knowledge:
        report.serialized = serialize.serialize(cfg, out_dir)
        report.warnings.extend(report.serialized.warnings)

    # [4] Grafo ANTES do dicionário: `technologies`, `services`, `entrypoints` e
    #     `data_stores` derivam de entidades. Regenerar o dicionário com o grafo
    #     desatualizado produz um arquivo vazio — e ele é a primeira coisa que o
    #     agente lê.
    if cfg.graph.enabled and (cfg.sync.auto_dictionary or cfg.sync.auto_federation):
        try:
            from ragx.graph.service import rebuild as rebuild_graph

            g = rebuild_graph(cfg)
            report.entities = g.stats.entities
            report.relations = g.stats.relations
        except Exception as exc:  # grafo é derivado; não derruba o sync
            report.warnings.append(f"grafo não reconstruído: {exc}")

    if cfg.sync.auto_dictionary:
        try:
            from ragx.dictionary import builder

            data, _ = builder.build(cfg)
            builder.write(cfg, data, out_dir)
            if not data.get("technologies") and not data.get("services"):
                report.warnings.append(
                    "dicionário saiu sem tecnologias nem serviços — verifique se o "
                    "grafo foi reconstruído (`ragx graph rebuild`)"
                )
        except Exception as exc:
            report.warnings.append(f"dicionário não regenerado: {exc}")

    if cfg.sync.auto_federation and cfg.federation.enabled:
        try:
            from ragx.federation import slice as fed_slice

            fed_slice.build(cfg, out_dir)
        except Exception as exc:
            report.warnings.append(f"fatia de federação não regenerada: {exc}")

    # [5] Board de tarefas: a DEFINICAO viaja no Git, a EXECUCAO fica aqui
    #     (ADR-0014). Reidratar ANTES de serializar para que o que veio do
    #     `git pull` entre antes de ser regravado.
    if cfg.tasks.enabled:
        try:
            from ragx.tasks import serialize as task_serialize

            hidratado = task_serialize.rehydrate(cfg, out_dir)
            if write_knowledge:
                gravado = task_serialize.serialize(cfg, out_dir)
                gravado.conflicts = hidratado.conflicts
                gravado.history_lost = hidratado.history_lost
                report.tasks = gravado
            else:
                report.tasks = hidratado
            for c in hidratado.conflicts:
                report.warnings.append(f"conflito de status resolvido -> {c}")
            if hidratado.history_lost:
                report.warnings.append(
                    "board reconstruido do Git; o historico de execucao local "
                    "nao volta (runs, tentativas, logs) - ver ADR-0014"
                )
        except Exception as exc:
            report.warnings.append(f"board de tarefas nao sincronizado: {exc}")

    if report.to_commit:
        with open_db(cfg.db_path) as conn:
            set_meta(conn, "last_sync_commit", report.to_commit)
            conn.commit()

    report.duration_ms = int((time.perf_counter() - t0) * 1000)
    return report


def resolve(cfg: Config, rel_path: str | None = None, out_dir: str = "knowledge") -> SyncReport:
    """Conflito em `knowledge/` se resolve REDERIVANDO do arquivo-fonte.

    Os artefatos são derivados; resolver conflito neles à mão é perda de tempo,
    a fonte de verdade é o código que o Git já mergeou.
    """
    if rel_path:
        for folder, ext in (("chunks", ".jsonl"), ("documents", ".json")):
            p = cfg.root / out_dir / folder / f"{serialize.artifact_name(rel_path)}{ext}"
            if p.is_file():
                p.unlink()
    return sync(cfg, full=bool(rel_path is None), out_dir=out_dir)

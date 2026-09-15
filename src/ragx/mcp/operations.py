"""Operações de ESCRITA expostas ao agente (ADR-0012).

O agente manda no índice: reindexar, sincronizar, reconstruir grafo e
dicionário, ligar e desligar o watcher, instalar conhecimento base. O que ele
continua sem poder fazer é exatamente o que o ADR-0006 proíbe e nada mais:

    PERMITIDO (novo)               CONTINUA PROIBIDO
    reindexar o projeto            ler um arquivo do disco
    sincronizar knowledge/         escapar do Security Gate
    reconstruir grafo/dicionário   indexar fora da raiz do projeto
    instalar fonte base            executar comando arbitrário

A diferença entre as duas colunas não é "quanto o agente pode", é QUE CAMINHO
o byte percorre. Toda escrita aqui chama o MESMO serviço que a CLI chama, e
todo conteúdo continua entrando por `iter_files` -> `SecurityGate.admit`. Um
agente com escrita liberada não consegue extrair um segredo do `.env`: não
existe função que devolva isso.

Este módulo não importa `os`, `pathlib`, `subprocess` nem cliente HTTP — o
teste arquitetural falha se alguém tentar. Ele orquestra serviços.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ragx.config import Config
from ragx.mcp.tools import err, ok

# Reindexação concorrente não corrompe (SQLite com WAL resolve), mas desperdiça:
# duas varreduras completas em paralelo pelo mesmo motivo. A segunda espera.
_LOCK = threading.Lock()
_BUSY_MSG = (
    "outra operação de escrita está em andamento — aguarde e repita; "
    "use get_status para acompanhar"
)


class WriteDisabledError(Exception):
    pass


def _exclusive(fn: Any, timeout_s: float) -> dict[str, Any]:
    if not _LOCK.acquire(timeout=timeout_s):
        return err("busy", _BUSY_MSG)
    try:
        t0 = time.perf_counter()
        data = fn()
        data["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return ok(data)
    finally:
        _LOCK.release()


class WriteAPI:
    """Fachada de escrita. Espelha a CLI, comando a comando."""

    def __init__(self, cfg: Config, enabled: bool):
        self.cfg = cfg
        self.enabled = enabled

    def _check(self) -> dict[str, Any] | None:
        if not self.enabled:
            return err(
                "write_disabled",
                "este servidor está em modo somente-leitura. "
                "Suba com `ragx mcp serve --write` ou defina [mcp] allow_write = true.",
            )
        return None

    # ── índice ──────────────────────────────────────────────────────────
    def reindex(self, full: bool = False, embed: bool = True) -> dict[str, Any]:
        """Varre o projeto e atualiza o índice. Incremental por padrão."""
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.indexing.pipeline import index_project

            r = index_project(self.cfg, full=full, embed=embed)
            return {
                "operation": "reindex",
                "full": full,
                "files_seen": r.stats.files_seen,
                "indexed": r.stats.indexed,
                "unchanged": r.stats.unchanged,
                "removed": r.stats.removed,
                "chunks": r.stats.chunks,
                "embedded": r.stats.embedded,
                # Contagem, nunca os caminhos: a lista de arquivos bloqueados é
                # um mapa de onde estão os segredos do repositório.
                "blocked": r.stats.blocked,
                "redacted": r.stats.redacted,
                "embed_error": (
                    r.embed_error.splitlines()[0] if r.embed_error else None
                ),
            }

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

    def sync(self, full: bool = False, write_knowledge: bool = True) -> dict[str, Any]:
        """Reidrata, reindexa, regrava `knowledge/`, grafo, dicionário e federação."""
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.sync.service import sync as run_sync

            r = run_sync(self.cfg, full=full, write_knowledge=write_knowledge)
            return {
                "operation": "sync",
                "mode": r.mode,
                "indexed": r.indexed,
                "unchanged": r.unchanged,
                "removed": r.removed,
                "embedded": r.embedded,
                "entities": r.entities,
                "relations": r.relations,
                "rehydrated_ok": r.rehydrate.ok,
                "rehydrate_mismatch": r.rehydrate.mismatch,
                "knowledge_bytes": (
                    r.serialized.bytes_written if r.serialized else 0
                ),
                "warnings": r.warnings[:10],
            }

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

    def rebuild_graph(self) -> dict[str, Any]:
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.graph.service import rebuild

            g = rebuild(self.cfg)
            return {
                "operation": "rebuild_graph",
                "entities": g.stats.entities,
                "relations": g.stats.relations,
            }

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

    def generate_dictionary(self) -> dict[str, Any]:
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.dictionary import builder

            data, _built = builder.build(self.cfg)
            written = builder.write(self.cfg, data)
            return {
                "operation": "generate_dictionary",
                "bytes": written.bytes_written,
                "sections": sorted(data),
                "technologies": len(data.get("technologies") or []),
                "services": len(data.get("services") or []),
            }

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

    # ── watcher ─────────────────────────────────────────────────────────
    def refresh(self) -> dict[str, Any]:
        """Uma passada do watcher: aplica o que mudou desde a última vez.

        É o que o agente chama ANTES de uma tarefa, para não raciocinar em
        cima de um índice velho. Barato quando nada mudou.
        """
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.watch.monitor import WatchState, apply_changes

            st = WatchState()
            apply_changes(self.cfg, st, consolidate=True)
            return {
                "operation": "refresh",
                "indexed": st.indexed,
                "blocked": st.blocked,
                "consolidated": st.consolidations > 0,
                "error": st.last_error,
                "warnings": st.warnings[:10],
            }

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

    # ── conhecimento base ───────────────────────────────────────────────
    def base_sources(self) -> dict[str, Any]:
        """Fontes de conhecimento base ativas nesta máquina. Leitura."""
        from ragx.base import source as base_source

        return ok({
            "sources": [
                {"name": s.name, "origin": s.origin, "files": s.files,
                 "commit": s.commit, "enabled": s.enabled}
                for s in base_source.load_registry(self.cfg)
            ],
            "required_by_project": list(self.cfg.base.sources),
            "prefix": f"{base_source.PREFIX}/",
        })

    def base_sync(self) -> dict[str, Any]:
        """Instala as fontes que o projeto exige e faltam. Só as DECLARADAS.

        O agente não escolhe a URL: ele aplica o que `ragx.toml` e
        `knowledge/base.json` já declaram. Um agente induzido por texto
        malicioso num README não consegue apontar a base para um repositório
        atacante — a origem vem de arquivo versionado, revisado por humano.
        """
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.base import source as base_source

            reports = base_source.sync_declared(
                self.cfg, base_source.declared_for(self.cfg)
            )
            return {
                "operation": "base_sync",
                "installed": [r.name for r in reports if not r.warnings],
                "failed": [
                    {"name": r.name, "reason": r.warnings[0]}
                    for r in reports if r.warnings
                ],
            }

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

    # ── federação ───────────────────────────────────────────────────────
    def publish_contract(self) -> dict[str, Any]:
        """Regera a superfície pública e publica no hub da máquina."""
        blocked = self._check()
        if blocked:
            return blocked

        def run() -> dict[str, Any]:
            from ragx.federation import hub
            from ragx.federation import slice as fed_slice

            built = fed_slice.build(self.cfg)
            out: dict[str, Any] = {
                "operation": "publish_contract",
                "provides": built.provides,
                "consumes": built.consumes,
                "contracts": built.contracts,
                "skipped_private": built.skipped_private,
                "warnings": built.warnings[:10],
            }
            # Sem hub nesta máquina, a fatia foi gerada e é isso — publicar num
            # hub que não existe não é erro, é um passo que não se aplica.
            if hub.hub_db(self.cfg).exists():
                pushed = hub.sync(self.cfg, only=self.cfg.project.name or None)
                out["hub_synced"] = pushed.synced
                out["hub_items"] = pushed.items
                out["warnings"] = (out["warnings"] + pushed.warnings)[:10]
            else:
                out["hub_synced"] = None
            return out

        return _exclusive(run, self.cfg.mcp.write_timeout_s)

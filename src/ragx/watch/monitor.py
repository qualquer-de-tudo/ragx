"""`ragx watch` — mantém o índice acompanhando o working tree.

Por polling de `size+mtime`, não por API do sistema operacional. Três razões:

  1. ZERO dependência nova. `watchdog` traria uma árvore de pacotes e um
     backend diferente por plataforma.
  2. É o MESMO sinal que o indexador incremental já usa para decidir o que
     reprocessar — watcher e indexador nunca discordam sobre o que mudou.
  3. Editor que salva via arquivo temporário + rename (quase todos) gera
     eventos confusos em API nativa; `stat` mostra só o resultado final.

O custo é o de um `stat` por arquivo não ignorado a cada ciclo — em um
repositório de alguns milhares de arquivos, milissegundos.

Duas velocidades, de propósito:
  • a cada mudança → reindexa (barato; mantém busca e documentos frescos)
  • a cada `full_sync_every` mudanças → consolida (grafo, dicionário,
    `knowledge/`), que é caro demais para rodar a cada Ctrl+S.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ragx.config import Config
from ragx.security.gate import SecurityGate
from ragx.walk import scan_fingerprints


@dataclass(frozen=True, slots=True)
class Delta:
    created: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.created) + len(self.modified) + len(self.deleted)

    @property
    def paths(self) -> tuple[str, ...]:
        return self.created + self.modified + self.deleted


@dataclass
class WatchState:
    cycles: int = 0
    applied: int = 0
    consolidations: int = 0
    indexed: int = 0
    blocked: int = 0
    since_consolidation: int = 0
    last_error: str | None = None
    warnings: list[str] = field(default_factory=list)


def diff(
    before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]
) -> Delta:
    created = tuple(sorted(p for p in after if p not in before))
    deleted = tuple(sorted(p for p in before if p not in after))
    modified = tuple(sorted(p for p in after if p in before and after[p] != before[p]))
    return Delta(created, modified, deleted)


def _gate(cfg: Config) -> SecurityGate:
    return SecurityGate(
        cfg.root,
        policy=cfg.security.policy,
        scan_content=cfg.security.scan_content,
        min_entropy=cfg.security.min_entropy,
        extra_exclude=cfg.index.exclude,
        extra_include=cfg.index.include,
    )


def snapshot(cfg: Config) -> dict[str, tuple[int, int]]:
    return scan_fingerprints(cfg.root, _gate(cfg), cfg.index.follow_symlinks)


def apply_changes(
    cfg: Config, state: WatchState, consolidate: bool, source: str = "watch"
) -> None:
    """Reindexa; consolida quando o ciclo pede.

    Nada aqui pode derrubar o laço: um watcher que morre no primeiro arquivo
    malformado é pior que nenhum watcher, porque o agente continua consultando
    um índice que parou no tempo sem ninguém perceber.
    """
    from ragx.core.errors import IndexBusyError
    from ragx.indexing.pipeline import index_project

    try:
        r = index_project(cfg, source=source)
        state.indexed += r.stats.indexed
        state.blocked += r.stats.blocked
        state.applied += 1
        state.since_consolidation += 1
        if r.embed_error:
            state.warnings.append(f"embeddings: {r.embed_error.splitlines()[0]}")
    except IndexBusyError:
        state.warnings.append("índice ocupado; atualização agendada")
        return
    except Exception as exc:
        state.last_error = f"index: {exc}"
        return

    if not consolidate:
        return

    try:
        from ragx.sync.service import sync as run_sync

        rep = run_sync(cfg)
        state.warnings.extend(rep.warnings)
        state.consolidations += 1
        state.since_consolidation = 0
    except Exception as exc:
        state.last_error = f"sync: {exc}"


def watch(
    cfg: Config,
    on_event: Callable[[str, Delta, WatchState], None] | None = None,
    max_cycles: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> WatchState:
    """Laço principal. `max_cycles` existe para o teste; em uso real é infinito.

    `on_event` recebe ("change"|"apply"|"idle", delta, state) — a apresentação
    fica toda na CLI, este módulo não imprime nada.
    """
    state = WatchState()
    known = snapshot(cfg)
    pendente: set[str] = set()
    ultimo_evento = 0.0

    while max_cycles is None or state.cycles < max_cycles:
        state.cycles += 1
        sleep(cfg.watch.interval_s)

        atual = snapshot(cfg)
        d = diff(known, atual)
        known = atual

        if d.total:
            # Trocou algo: o relógio do debounce reinicia. Salvar 12 arquivos em
            # sequência vira UMA reindexação, não doze.
            pendente.update(d.paths[: cfg.watch.max_batch])
            ultimo_evento = time.monotonic()
            if on_event:
                on_event("change", d, state)
            continue

        if not pendente:
            if on_event:
                on_event("idle", d, state)
            continue

        if time.monotonic() - ultimo_evento < cfg.watch.debounce_s:
            continue

        lote = Delta(modified=tuple(sorted(pendente)))
        pendente.clear()
        consolidar = state.since_consolidation + 1 >= cfg.watch.full_sync_every
        apply_changes(cfg, state, consolidate=consolidar)
        if on_event:
            on_event("apply", lote, state)

    return state

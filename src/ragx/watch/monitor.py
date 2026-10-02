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

import statistics
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
    #: duração do último ciclo e mediana dos ociosos, em ms (RAGX-0147)
    last_cycle_ms: float | None = None
    idle_cycle_ms_p50: float | None = None
    _idle_ms: list[float] = field(default_factory=list, repr=False)


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


#: arquivos cujo conteúdo muda o que é visitado: o gate (e o cache de veredito) é refeito quando um deles muda
_ARQUIVOS_DE_REGRA = frozenset({".gitignore", ".dockerignore", ".ragignore"})
_JANELA_OCIOSA = 200


def _mexe_em_regra(paths: tuple[str, ...]) -> bool:
    return any(p.rsplit("/", 1)[-1] in _ARQUIVOS_DE_REGRA for p in paths)


def snapshot(
    cfg: Config,
    gate: SecurityGate | None = None,
    ignored_cache: dict[str, bool] | None = None,
) -> dict[str, tuple[int, int]]:
    """Sem `gate` constrói um (como sempre); o laço do `watch` passa o dele (RAGX-0147)."""
    return scan_fingerprints(cfg.root, gate or _gate(cfg), cfg.index.follow_symlinks, ignored_cache)


def _atualizar_grafo(cfg: Config, state: WatchState, tocados: list[str]) -> None:
    """Grafo só dos documentos tocados (RAGX-0151). Falha vira aviso: nunca derruba a indexação já feita.

    Quando consolida, o `sync` refaz o grafo completo e esta chamada não acontece.
    """
    try:
        from ragx.graph.service import update_documents

        update_documents(cfg, tocados)
    except Exception as exc:
        state.warnings.append(f"grafo: {type(exc).__name__}: {exc}")


def apply_changes(
    cfg: Config,
    state: WatchState,
    consolidate: bool,
    source: str = "watch",
    paths: tuple[str, ...] | None = None,
    gate: SecurityGate | None = None,
) -> None:
    """Reindexa; consolida quando o ciclo pede.

    Nada aqui pode derrubar o laço: um watcher que morre no primeiro arquivo
    malformado é pior que nenhum watcher, porque o agente continua consultando
    um índice que parou no tempo sem ninguém perceber.
    """
    from ragx.core.errors import IndexBusyError
    from ragx.indexing.pipeline import index_paths, index_project

    try:
        # Lote de arquivos conhecidos: reindexa só eles (RAGX-0140). `index_paths` cai sozinho no
        # índice completo para arquivo de regra ou lote acima de `watch.max_batch`.
        if paths:
            r = index_paths(cfg, paths, source=source, gate=gate)
        else:
            r = index_project(cfg, source=source)
        state.indexed += r.stats.indexed
        state.blocked += r.stats.blocked
        state.applied += 1
        state.since_consolidation += 1
        if r.embed_error:
            state.warnings.append(f"embeddings: {r.embed_error.splitlines()[0]}")
        if not consolidate and r.touched_documents:
            _atualizar_grafo(cfg, state, r.touched_documents)
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
    gate = _gate(cfg)  # uma vez por sessão: reconstruído só quando um arquivo de ignore muda
    vereditos: dict[str, bool] = {}
    known = snapshot(cfg, gate, vereditos)
    pendente: set[str] = set()
    ultimo_evento = 0.0

    while max_cycles is None or state.cycles < max_cycles:
        state.cycles += 1
        sleep(cfg.watch.interval_s)
        inicio = time.perf_counter()

        atual = snapshot(cfg, gate, vereditos)
        d = diff(known, atual)
        known = atual

        if d.total and _mexe_em_regra(d.paths):
            # `.gitignore` & cia mudou: o que é visitado muda. Gate novo, vereditos zerados e uma
            # varredura nova, para o ciclo seguinte já refletir a regra.
            gate = _gate(cfg)
            vereditos.clear()
            known = snapshot(cfg, gate, vereditos)

        if d.total:
            # Trocou algo: o relógio do debounce reinicia. Salvar 12 arquivos em
            # sequência vira UMA reindexação, não doze.
            pendente.update(d.paths[: cfg.watch.max_batch])
            ultimo_evento = time.monotonic()
            _fim_do_ciclo(state, inicio, ocioso=False)
            if on_event:
                on_event("change", d, state)
            continue

        if not pendente:
            _fim_do_ciclo(state, inicio, ocioso=True)
            if on_event:
                on_event("idle", d, state)
            continue

        if time.monotonic() - ultimo_evento < cfg.watch.debounce_s:
            continue

        lote = Delta(modified=tuple(sorted(pendente)))
        pendente.clear()
        consolidar = state.since_consolidation + 1 >= cfg.watch.full_sync_every
        apply_changes(cfg, state, consolidate=consolidar, paths=lote.modified, gate=gate)
        if on_event:
            on_event("apply", lote, state)

    return state


def _fim_do_ciclo(state: WatchState, inicio: float, ocioso: bool) -> None:
    ms = (time.perf_counter() - inicio) * 1000
    state.last_cycle_ms = round(ms, 2)
    if ocioso:
        state._idle_ms.append(ms)
        del state._idle_ms[:-_JANELA_OCIOSA]
        state.idle_cycle_ms_p50 = round(statistics.median(state._idle_ms), 2)

"""Leitura, Gate, parse e chunking em paralelo para o primeiro índice (RAGX-0152).

O primeiro índice (e o `--full`) lia, passava pelo Gate, parseava e fatiava um arquivo de cada vez; num
projeto com milhares de arquivos isso era a maior parte do tempo. Aqui o estágio caro vai para um pool de
PROCESSOS, e o processo principal continua sendo o único que escreve no banco:

    varredura (principal) ──> Candidate ──> worker: read_candidate + parse + chunk ──> principal: upsert

- A varredura e as decisões baratas (`walk.iter_candidates`: ignore, veredito guardado, `unchanged`, tamanho,
  nome na deny-list) ficam no principal e não mudam.
- Cada worker constrói UM `SecurityGate` completo (inclusive o `IgnoreEngine`): o Gate não tem atalho
  (ADR-0008). Todo byte é lido por `walk.read_candidate`, e este módulo nunca abre arquivo por conta própria.
- Os resultados voltam NA ORDEM da varredura, de modo que a escrita é a mesma do caminho sequencial.
- Abaixo de `PARALLEL_MIN_FILES` candidatos a ler, ou com `jobs = 1`, nada disto roda: nenhum pool é criado.
- Se a infraestrutura do pool cair (processo morto, `spawn` que não consegue reimportar o módulo principal), o
  lote em andamento e o resto da rodada são refeitos no processo principal. Erro do NOSSO código num arquivo
  (`WorkerError`) não é infraestrutura: propaga, com o caminho.

Este módulo não importa `ragx.config` nem `typer`: cada worker em `spawn` pagaria o custo de importá-los.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import signal
from collections import deque
from collections.abc import Iterable, Iterator
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace

from ragx.core.ids import content_hash
from ragx.core.models import Chunk, DocKind
from ragx.indexing import parsers
from ragx.indexing.chunkers import ChunkOptions, chunk_document
from ragx.security.gate import SecurityGate
from ragx.walk import Candidate, WalkedFile, read_candidate

#: candidatos a ler a partir dos quais vale pagar a criação do pool (o `spawn` custa ~1 s por rodada)
PARALLEL_MIN_FILES = 200
#: candidatos por lote enviado a um worker
BATCH_FILES = 16
#: teto de workers quando `jobs = 0` (cada um custa 100–200 MB de RAM)
MAX_AUTO_JOBS = 4
#: lotes em voo por worker: limita a memória se o escritor for o gargalo
WINDOW_PER_WORKER = 4
#: um lote também fecha quando junta tantas entradas (decididas ou não), para a ordem fluir em rodadas com
#: poucos candidatos no meio de muitos arquivos `unchanged`
MAX_ENTRIES_PER_BATCH = 256


class WorkerError(Exception):
    """Falha do nosso código ao processar um arquivo no worker; a mensagem leva o caminho."""


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    """O que cada worker precisa para construir o PRÓPRIO Gate e o chunker. Só dados simples."""

    root: str
    policy: str
    scan_content: bool
    min_entropy: float
    extra_exclude: tuple[str, ...]
    extra_include: tuple[str, ...]
    max_tokens: int
    min_tokens: int
    include_unknown: bool


@dataclass(frozen=True, slots=True)
class Prepared:
    """Parse e chunking de um arquivo ADMITIDO, feitos no worker. `supported = False`: extensão fora da lista."""

    supported: bool
    chash: str
    doc_kind: DocKind | None = None
    lang: str | None = None
    title: str | None = None
    degraded: bool = False
    chunks: tuple[Chunk, ...] = ()


@dataclass
class ParallelStats:
    """O que a rodada fez de fato, para o relatório e para os testes."""

    jobs: int = 0  # 0 = nenhum pool foi criado
    batches: int = 0
    fell_back: str | None = None  # motivo, quando o pool caiu e o resto foi refeito no principal


def resolve_jobs(jobs: int) -> int:
    """`0` = `min(cpu_count, 4)`; `1` = sequencial; `N` = N workers."""
    if jobs <= 0:
        return max(1, min(os.cpu_count() or 1, MAX_AUTO_JOBS))
    return jobs


# ── worker ──────────────────────────────────────────────────────────────
_STATE: dict[str, object] = {}


def init_worker(spec: WorkerSpec) -> None:
    """Roda uma vez em cada worker: Gate COMPLETO (nenhum atalho), opções do chunker, Ctrl+C ignorado.

    O Ctrl+C é do processo principal: ele cancela o pool e espera os lotes em voo; um worker que morresse
    com `KeyboardInterrupt` deixaria o pool quebrado no meio do desligamento.
    """
    with contextlib.suppress(ValueError, OSError):  # fora do thread principal: nada a fazer
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    _STATE["spec"] = spec
    _STATE["opts"] = ChunkOptions(max_tokens=spec.max_tokens, min_tokens=spec.min_tokens)
    _STATE["gate"] = SecurityGate(
        spec.root,  # type: ignore[arg-type]
        policy=spec.policy,
        scan_content=spec.scan_content,
        min_entropy=spec.min_entropy,
        extra_exclude=list(spec.extra_exclude),
        extra_include=list(spec.extra_include),
    )


def prepare(rel_path: str, text: str, include_unknown: bool, opts: ChunkOptions) -> Prepared:
    """Hash, parse e chunking de um texto JÁ admitido pelo Gate."""
    chash = content_hash(text)
    parsed = parsers.parse(rel_path, text, include_unknown=include_unknown)
    if parsed is None:
        return Prepared(supported=False, chash=chash)
    return Prepared(
        supported=True,
        chash=chash,
        doc_kind=parsed.doc_kind,
        lang=parsed.lang,
        title=parsed.title,
        degraded=parsed.degraded,
        chunks=tuple(chunk_document(rel_path, text, parsed, opts)),
    )


def process_batch(batch: list[Candidate]) -> list[tuple[WalkedFile | None, Prepared | None]]:
    """Lê (com o Gate) e prepara cada candidato do lote. Um item por candidato, na mesma ordem."""
    gate = _STATE["gate"]
    spec = _STATE["spec"]
    opts = _STATE["opts"]
    saida: list[tuple[WalkedFile | None, Prepared | None]] = []
    for candidato in batch:
        try:
            walked = read_candidate(candidato, gate)  # type: ignore[arg-type]
            prepared = None
            if walked is not None and walked.decision.admitted:
                texto = walked.decision.content or ""
                prepared = prepare(walked.rel_path, texto, spec.include_unknown, opts)  # type: ignore[attr-defined,arg-type]
                # o texto já foi usado: não atravessa o processo de volta
                walked = replace(walked, decision=replace(walked.decision, content=None))
        except Exception as exc:
            raise WorkerError(f"{candidato.rel}: {type(exc).__name__}: {exc}") from exc
        saida.append((walked, prepared))
    return saida


# ── processo principal ──────────────────────────────────────────────────
Item = WalkedFile | Candidate


@dataclass
class _Lote:
    entradas: list[Item]
    futuro: Future[list[tuple[WalkedFile | None, Prepared | None]]] | None = None
    candidatos: int = field(default=0)


def process_stream(
    itens: Iterable[Item],
    gate: SecurityGate,
    spec: WorkerSpec,
    jobs: int,
    stats: ParallelStats | None = None,
) -> Iterator[tuple[WalkedFile, Prepared | None]]:
    """Entrega `(WalkedFile, Prepared | None)` NA ORDEM de `itens`.

    Os `Candidate` são lidos, passam pelo Gate e são preparados por um pool de `jobs` processos quando há pelo
    menos `PARALLEL_MIN_FILES` deles; senão (ou com `jobs = 1`) são lidos aqui mesmo, um a um, e `Prepared`
    vem `None` (o pipeline prepara no caminho de sempre). Os itens já decididos passam direto.
    """
    stats = stats if stats is not None else ParallelStats()
    fonte = iter(itens)
    buffer: list[Item] = []
    candidatos = 0
    minimo = PARALLEL_MIN_FILES
    if jobs > 1:
        for item in fonte:
            buffer.append(item)
            if isinstance(item, Candidate):
                candidatos += 1
                if candidatos >= minimo:
                    break
        else:
            jobs = 1  # a rodada inteira coube abaixo do limiar: sem pool
    if jobs <= 1:
        for item in _encadear(buffer, fonte):
            yield from _sequencial(item, gate)
        return
    yield from _paralelo(_encadear(buffer, fonte), gate, spec, jobs, stats)


def _encadear(buffer: list[Item], resto: Iterator[Item]) -> Iterator[Item]:
    yield from buffer
    yield from resto


def _sequencial(item: Item, gate: SecurityGate) -> Iterator[tuple[WalkedFile, Prepared | None]]:
    if isinstance(item, Candidate):
        lido = read_candidate(item, gate)
        if lido is not None:
            yield lido, None
    else:
        yield item, None


def _paralelo(
    itens: Iterator[Item], gate: SecurityGate, spec: WorkerSpec, jobs: int, stats: ParallelStats
) -> Iterator[tuple[WalkedFile, Prepared | None]]:
    janela = WINDOW_PER_WORKER * jobs
    pool: ProcessPoolExecutor | None = None
    pendentes: deque[_Lote] = deque()
    atual = _Lote([])
    try:
        pool = ProcessPoolExecutor(
            max_workers=jobs,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=init_worker,
            initargs=(spec,),
        )
        stats.jobs = jobs
        for item in itens:
            atual.entradas.append(item)
            if isinstance(item, Candidate):
                atual.candidatos += 1
            if atual.candidatos >= BATCH_FILES or len(atual.entradas) >= MAX_ENTRIES_PER_BATCH:
                pendentes.append(_enviar(pool, atual, stats))
                atual = _Lote([])
                while len(pendentes) >= janela:
                    yield from _colher(pendentes.popleft(), gate, stats)
                while pendentes and (pendentes[0].futuro is None or pendentes[0].futuro.done()):
                    yield from _colher(pendentes.popleft(), gate, stats)
        if atual.entradas:
            pendentes.append(_enviar(pool, atual, stats))
        while pendentes:
            yield from _colher(pendentes.popleft(), gate, stats)
    finally:
        if pool is not None:
            # Ctrl+C, erro de worker ou consumidor que parou: cancela o que não começou e espera só os lotes
            # em voo (poucos arquivos), para não sobrar processo filho.
            pool.shutdown(wait=True, cancel_futures=True)


def _enviar(pool: ProcessPoolExecutor, lote: _Lote, stats: ParallelStats) -> _Lote:
    candidatos = [e for e in lote.entradas if isinstance(e, Candidate)]
    if not candidatos or stats.fell_back is not None:
        return lote  # nada a processar fora, ou o pool já caiu: `_colher` lê aqui
    try:
        lote.futuro = pool.submit(process_batch, candidatos)
        stats.batches += 1
    except BrokenProcessPool as exc:
        stats.fell_back = f"pool indisponível ({type(exc).__name__})"
    return lote


def _colher(lote: _Lote, gate: SecurityGate, stats: ParallelStats) -> Iterator[tuple[WalkedFile, Prepared | None]]:
    resultados: list[tuple[WalkedFile | None, Prepared | None]] | None = None
    if lote.futuro is not None:
        try:
            resultados = lote.futuro.result()
        except BrokenProcessPool as exc:
            stats.fell_back = f"pool quebrou ({type(exc).__name__}); o resto da rodada rodou no processo principal"
    proximo = iter(resultados) if resultados is not None else None
    for entrada in lote.entradas:
        if not isinstance(entrada, Candidate):
            yield entrada, None
            continue
        if proximo is not None:
            walked, prepared = next(proximo)
        else:
            walked, prepared = read_candidate(entrada, gate), None
        if walked is not None:
            yield walked, prepared

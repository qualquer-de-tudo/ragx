import { spawn as nodeSpawn } from 'node:child_process'
import { ragxCommand } from '../system/ragx-exe'
import type { ResolvedJob, Step } from './catalog'
import type { JobView, JobState } from '../../src/types/ragx-bridge'

export type SpawnFn = (cmd: string, args: string[], cwd: string | null) => ChildLike

export interface ChildLike {
  onStdoutLine(cb: (line: string) => void): void
  onStderrLine(cb: (line: string) => void): void
  onExit(cb: (code: number | null) => void): void
  kill(): void
}

export interface QueueDeps {
  spawn: SpawnFn
  now: () => number
  newId: () => string
}

const MAX_LOG_TAIL = 20
const MAX_FINISHED_HISTORY = 20
const BUSY_NOTE = 'Outra indexação estava rodando; este pedido ficou agendado.'
const MAX_ERROR_LENGTH = 300

interface ProgressLine {
  phase?: unknown
  done?: unknown
  total?: unknown
}

function parseProgressLine(line: string): ProgressLine | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(line)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null) return null
  const obj = parsed as ProgressLine
  if (typeof obj.phase !== 'string') return null
  return obj
}

function asNumberOrNull(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

interface InternalJob {
  view: JobView
  resolved: ResolvedJob
  /** Index (0-based) do passo em execução (ou do próximo, se ainda `queued`). */
  stepIndex: number
  /** Quando a fase atual começou (`deps.now()`), para calcular `etaSeconds`/`ratePerSecond`. */
  phaseStartedAt: number | null
  child: ChildLike | null
  cancelRequested: boolean
  lastStdoutLine: string | null
  lastStderrLine: string | null
}

/**
 * Fila serial de tarefas: no máximo uma `running` por vez (o Ollama é
 * compartilhado - ver global-constraints.md). Passos de uma tarefa rodam em
 * sequência, e só o código de saída decide o que fazer a seguir; linhas de
 * progresso (`--progress`) só atualizam campos de exibição.
 */
export class JobQueue {
  private readonly deps: QueueDeps
  private readonly onChange: (jobs: JobView[]) => void
  private readonly jobs: InternalJob[] = []
  private readonly finished: InternalJob[] = []

  constructor(deps: QueueDeps, onChange: (jobs: JobView[]) => void) {
    this.deps = deps
    this.onChange = onChange
  }

  enqueue(job: ResolvedJob): JobView {
    const existing = this.jobs.find((j) => j.resolved.kind === job.kind && j.resolved.projectId === job.projectId)
    if (existing) return existing.view

    const nowIso = new Date(this.deps.now()).toISOString()
    const internal: InternalJob = {
      view: {
        id: this.deps.newId(),
        kind: job.kind,
        label: job.label,
        projectId: job.projectId,
        state: 'queued',
        step: 1,
        steps: job.steps.length,
        phase: null,
        done: null,
        total: null,
        etaSeconds: null,
        ratePerSecond: null,
        note: null,
        error: null,
        logTail: [],
        queuedAt: nowIso,
        startedAt: null,
        finishedAt: null,
      },
      resolved: job,
      stepIndex: 0,
      phaseStartedAt: null,
      child: null,
      cancelRequested: false,
      lastStdoutLine: null,
      lastStderrLine: null,
    }
    this.jobs.push(internal)
    this.notify()
    this.pump()
    return internal.view
  }

  cancel(id: string): boolean {
    const job = this.jobs.find((j) => j.view.id === id)
    if (!job) return false

    if (job.view.state === 'queued') {
      this.removeFromActive(job)
      this.finish(job, 'cancelled')
      this.notify()
      this.pump()
      return true
    }

    if (job.view.state === 'running') {
      job.cancelRequested = true
      job.child?.kill()
      return true
    }

    return false
  }

  list(): JobView[] {
    const active = this.jobs.map((j) => j.view)
    // `this.finished` já é mantido com no máximo `MAX_FINISHED_HISTORY`
    // entradas (ver `finish()`) - mais recente primeiro.
    const finished = this.finished
      .slice()
      .reverse()
      .map((j) => j.view)
    return [...active, ...finished]
  }

  hasActive(): boolean {
    return this.jobs.length > 0
  }

  busyProjectIds(): Set<string> {
    const ids = new Set<string>()
    for (const j of this.jobs) {
      if (j.view.projectId !== null) ids.add(j.view.projectId)
    }
    return ids
  }

  // -- internals ----------------------------------------------------------

  private notify(): void {
    this.onChange(this.list())
  }

  private removeFromActive(job: InternalJob): void {
    const idx = this.jobs.indexOf(job)
    if (idx >= 0) this.jobs.splice(idx, 1)
  }

  /** Garante que a tarefa `running` (se houver) esteja de fato processando um passo. */
  private pump(): void {
    const running = this.jobs.find((j) => j.view.state === 'running')
    if (running) return // já tem uma em andamento - a fila é serial

    const next = this.jobs.find((j) => j.view.state === 'queued')
    if (!next) return

    next.view.state = 'running'
    next.view.startedAt = new Date(this.deps.now()).toISOString()
    this.startStep(next)
  }

  private startStep(job: InternalJob): void {
    job.view.step = job.stepIndex + 1
    job.view.phase = null
    job.view.done = null
    job.view.total = null
    job.view.etaSeconds = null
    job.view.ratePerSecond = null
    job.phaseStartedAt = null
    job.lastStdoutLine = null
    job.lastStderrLine = null

    const step: Step = job.resolved.steps[job.stepIndex]
    const child = this.deps.spawn(step.cmd, step.args, step.cwd)
    job.child = child

    child.onStdoutLine((line) => this.onLine(job, 'stdout', line))
    child.onStderrLine((line) => this.onLine(job, 'stderr', line))
    child.onExit((code) => this.onExit(job, code))

    this.notify()
  }

  private onLine(job: InternalJob, source: 'stdout' | 'stderr', line: string): void {
    job.view.logTail.push(line)
    if (job.view.logTail.length > MAX_LOG_TAIL) {
      job.view.logTail.splice(0, job.view.logTail.length - MAX_LOG_TAIL)
    }

    if (line.trim().length > 0) {
      if (source === 'stdout') job.lastStdoutLine = line
      else job.lastStderrLine = line
    }

    if (source === 'stdout') {
      const parsed = parseProgressLine(line)
      if (parsed) this.applyProgress(job, parsed)
    }

    this.notify()
  }

  private applyProgress(job: InternalJob, parsed: ProgressLine): void {
    const phase = parsed.phase as string

    if (phase === 'busy') {
      job.view.note = BUSY_NOTE
      return
    }

    if (phase !== 'scan' && phase !== 'chunk' && phase !== 'embed') return // inclui 'done' - o fim vem do código de saída

    const nowMs = this.deps.now()
    if (job.view.phase !== phase) {
      job.view.phase = phase
      job.phaseStartedAt = nowMs
    }
    job.view.done = asNumberOrNull(parsed.done)
    job.view.total = asNumberOrNull(parsed.total)

    const elapsedSeconds = (nowMs - (job.phaseStartedAt ?? nowMs)) / 1000
    const haveProgress = job.view.total !== null && job.view.total > 0 && job.view.done !== null && job.view.done > 0

    job.view.etaSeconds =
      haveProgress && elapsedSeconds > 0
        ? Math.round(((job.view.total as number) - (job.view.done as number)) * (elapsedSeconds / (job.view.done as number)))
        : null

    job.view.ratePerSecond =
      phase === 'embed' && haveProgress && elapsedSeconds > 0 ? (job.view.done as number) / elapsedSeconds : null
  }

  private onExit(job: InternalJob, code: number | null): void {
    if (job.cancelRequested) {
      this.removeFromActive(job)
      this.finish(job, 'cancelled')
      this.notify()
      this.pump()
      return
    }

    if (code === 0) {
      const isLastStep = job.stepIndex + 1 >= job.resolved.steps.length
      if (!isLastStep) {
        job.stepIndex += 1
        this.startStep(job)
        return
      }
      this.removeFromActive(job)
      this.finish(job, 'done')
      this.notify()
      this.pump()
      return
    }

    const lastLine = job.lastStderrLine ?? job.lastStdoutLine
    job.view.error = lastLine !== null ? lastLine.slice(0, MAX_ERROR_LENGTH) : `código de saída ${String(code)}`
    this.removeFromActive(job)
    this.finish(job, 'failed')
    this.notify()
    this.pump()
  }

  private finish(job: InternalJob, state: JobState): void {
    job.view.state = state
    job.view.finishedAt = new Date(this.deps.now()).toISOString()
    job.child = null
    this.finished.push(job)
    // `list()` só expõe as últimas `MAX_FINISHED_HISTORY` - sem isso, um
    // painel aberto por muito tempo acumula `JobView` (com `logTail`) sem
    // limite, mesmo nunca aparecendo na lista.
    if (this.finished.length > MAX_FINISHED_HISTORY) {
      this.finished.splice(0, this.finished.length - MAX_FINISHED_HISTORY)
    }
  }
}

// -- defaultSpawn -----------------------------------------------------------

/** Quebra um stream em linhas: a última linha parcial de cada pedaço espera o próximo antes de ser emitida. */
function lineBuffer(emit: (line: string) => void) {
  let pending = ''
  return {
    push(chunk: string): void {
      pending += chunk
      const lines = pending.split(/\r?\n/)
      pending = lines.pop() ?? ''
      for (const line of lines) emit(line)
    },
    flush(): void {
      if (pending.length > 0) {
        emit(pending)
        pending = ''
      }
    },
  }
}

/**
 * `spawn` real, sem shell (obrigatório - ver global-constraints.md), com
 * timeout deixado para quem chama (a fila não impõe um: tarefas de indexação
 * legitimamente demoram). `'ragx'` resolve para o caminho absoluto achado
 * por `ragxCommand()` (fora do PATH do app aberto pelo menu Iniciar).
 */
export function defaultSpawn(): SpawnFn {
  return (cmd, args, cwd) => {
    const resolvedCmd = cmd === 'ragx' ? ragxCommand() : cmd
    const child = nodeSpawn(resolvedCmd, args, { cwd: cwd ?? undefined, windowsHide: true })

    let outCb: (line: string) => void = () => {}
    let errCb: (line: string) => void = () => {}
    let exitCb: (code: number | null) => void = () => {}
    // Node emite `error` e depois ainda `close` quando o processo nem chega
    // a nascer (ex.: ENOENT) - sem essa guarda, `exitCb` seria chamado duas
    // vezes para a mesma tarefa.
    let settled = false

    const outBuf = lineBuffer((l) => outCb(l))
    const errBuf = lineBuffer((l) => errCb(l))

    child.stdout?.on('data', (chunk: Buffer) => outBuf.push(chunk.toString('utf-8')))
    child.stderr?.on('data', (chunk: Buffer) => errBuf.push(chunk.toString('utf-8')))

    // `close` (não `exit`): garante que os streams de stdio já terminaram de
    // entregar dados antes de soltar o resto do buffer e avisar quem chamou.
    child.on('close', (code) => {
      if (settled) return
      settled = true
      outBuf.flush()
      errBuf.flush()
      exitCb(code)
    })
    child.on('error', () => {
      if (settled) return
      settled = true
      outBuf.flush()
      errBuf.flush()
      exitCb(null)
    })

    return {
      onStdoutLine: (cb) => {
        outCb = cb
      },
      onStderrLine: (cb) => {
        errCb = cb
      },
      onExit: (cb) => {
        exitCb = cb
      },
      kill: () => {
        child.kill()
      },
    }
  }
}

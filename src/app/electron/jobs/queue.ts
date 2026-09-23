import { spawn as nodeSpawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import { StringDecoder } from 'node:string_decoder'
import { ragxCommand } from '../system/ragx-exe'
import type { ResolvedJob, Step } from './catalog'
import type { JobKind, JobView, JobState } from '../../src/types/ragx-bridge'

export type SpawnFn = (cmd: string, args: string[], cwd: string | null) => ChildLike

/**
 * `spawnError` só vem quando o processo nem chegou a nascer (ENOENT etc.):
 * aí `code` é `null` e o texto já está pronto para o usuário.
 */
export type ExitCallback = (code: number | null, spawnError?: string) => void

export interface ChildLike {
  onStdoutLine(cb: (line: string) => void): void
  onStderrLine(cb: (line: string) => void): void
  onExit(cb: ExitCallback): void
  kill(): void
}

export interface QueueDeps {
  spawn: SpawnFn
  now: () => number
  newId: () => string
  /**
   * Checagem para passos com `onlyIfGitRepo` (hooks do `add-project`): a
   * pasta está dentro de um repositório git? Sem ela, o passo roda sempre.
   */
  isGitRepo?: (folder: string) => Promise<boolean>
  /**
   * Conferência depois do último passo sair com 0. Devolve o texto do erro
   * quando a tarefa, apesar dos códigos de saída, não fez o que prometia
   * (ex.: `add-project` que não entrou no hub); `null` quando está tudo certo.
   */
  verify?: (job: ResolvedJob) => string | null
}

const MAX_LOG_TAIL = 20
const MAX_STDERR_LINES = 50
const MAX_FINISHED_HISTORY = 20
const MAX_ERROR_LENGTH = 300

/** `IndexBusyError.exit_code` no core (`ragx sync`, `graph`, `dictionary` com a trava ocupada). */
const BUSY_EXIT_CODE = 4
const BUSY_EXIT_NOTE = 'Outra indexação estava rodando. Tente de novo quando ela terminar.'
const NO_GIT_NOTE = 'Sem hooks: a pasta não é um repositório git.'

/**
 * Nota da linha `{"phase":"busy"}` de `ragx index --progress`. O core drena o
 * pedido agendado como indexação INCREMENTAL, então a nota diz o que de fato
 * vai acontecer para cada tipo de tarefa.
 */
const BUSY_NOTE_DEFAULT = 'Outra indexação estava rodando; este pedido ficou agendado.'
const BUSY_NOTES: Partial<Record<JobKind, string>> = {
  embed: 'Outra indexação estava rodando; os embeddings faltantes serão gerados quando ela terminar.',
  'reindex-full': 'Outra indexação estava rodando. Peça Reindexar do zero de novo quando ela terminar.',
}

interface ProgressLine {
  phase?: unknown
  done?: unknown
  total?: unknown
  embed_error?: unknown
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

function firstLine(text: string): string {
  return text.split(/\r\n|\n|\r/)[0].trim()
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
  /** stderr do passo atual (as últimas `MAX_STDERR_LINES`), para montar o texto do erro. */
  stderrLines: string[]
  /** Primeira linha de `embed_error` da linha `done` de algum passo `--progress`. */
  embedError: string | null
}

/**
 * Fila serial de tarefas: no máximo uma `running` por vez (o Ollama é
 * compartilhado - ver global-constraints.md). Passos de uma tarefa rodam em
 * sequência, e o código de saída decide o que fazer a seguir; das linhas de
 * progresso (`--progress`), só a `done` pesa no resultado (`embed_error`).
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
    // Não é só `kind`+`projectId`: kinds sem projeto (`ollama-pull`,
    // `add-project`) teriam `projectId` sempre `null`, o que faria dois
    // pedidos genuinamente diferentes (modelos ou pastas distintas)
    // colidir num só. `dedupeKey` (Task 5, fix round 1) já carrega o que
    // distingue cada pedido - ver `catalog.ts`.
    const existing = this.jobs.find((j) => j.resolved.dedupeKey === job.dedupeKey)
    if (existing) return existing.view

    const nowIso = new Date(this.deps.now()).toISOString()
    const internal: InternalJob = {
      view: {
        id: this.deps.newId(),
        kind: job.kind,
        label: job.label,
        projectId: job.projectId,
        model: job.model,
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
      stderrLines: [],
      embedError: null,
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
      this.end(job, 'cancelled')
      return true
    }

    if (job.view.state === 'running') {
      // Sem processo (ex.: esperando a checagem de git de um passo), o
      // pedido é atendido quando a checagem voltar - ver `startStep`.
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

  private addNote(job: InternalJob, text: string): void {
    const current = job.view.note
    if (current === null) job.view.note = text
    else if (!current.includes(text)) job.view.note = `${current} ${text}`
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
    job.stderrLines = []
    job.child = null

    const step: Step = job.resolved.steps[job.stepIndex]
    const isGitRepo = this.deps.isGitRepo
    if (step.onlyIfGitRepo !== undefined && isGitRepo) {
      this.notify()
      let check: Promise<boolean>
      try {
        check = isGitRepo(step.onlyIfGitRepo)
      } catch {
        check = Promise.resolve(false)
      }
      check
        .catch(() => false)
        .then((inRepo) => {
          if (job.cancelRequested) {
            this.end(job, 'cancelled')
            return
          }
          if (!inRepo) {
            this.addNote(job, NO_GIT_NOTE)
            this.stepSucceeded(job)
            return
          }
          this.spawnStep(job, step)
        })
      return
    }
    this.spawnStep(job, step)
  }

  private spawnStep(job: InternalJob, step: Step): void {
    const child = this.deps.spawn(step.cmd, step.args, step.cwd)
    job.child = child

    child.onStdoutLine((line) => this.onLine(job, 'stdout', line))
    child.onStderrLine((line) => this.onLine(job, 'stderr', line))
    child.onExit((code, spawnError) => this.onExit(job, code, spawnError))

    this.notify()
  }

  private onLine(job: InternalJob, source: 'stdout' | 'stderr', line: string): void {
    job.view.logTail.push(line)
    if (job.view.logTail.length > MAX_LOG_TAIL) {
      job.view.logTail.splice(0, job.view.logTail.length - MAX_LOG_TAIL)
    }

    if (source === 'stdout') {
      if (line.trim().length > 0) job.lastStdoutLine = line
      const parsed = parseProgressLine(line)
      if (parsed) this.applyProgress(job, parsed)
    } else {
      job.stderrLines.push(line)
      if (job.stderrLines.length > MAX_STDERR_LINES) {
        job.stderrLines.splice(0, job.stderrLines.length - MAX_STDERR_LINES)
      }
    }

    this.notify()
  }

  private applyProgress(job: InternalJob, parsed: ProgressLine): void {
    const phase = parsed.phase as string

    if (phase === 'busy') {
      this.addNote(job, BUSY_NOTES[job.resolved.kind] ?? BUSY_NOTE_DEFAULT)
      return
    }

    if (phase === 'done') {
      // `ragx index --progress` sai com 0 mesmo quando o embedder falha; só
      // esta linha conta que nada foi gerado.
      const embedError = parsed.embed_error
      if (typeof embedError === 'string' && embedError.trim().length > 0) {
        job.embedError = firstLine(embedError)
      }
      return
    }

    if (phase !== 'scan' && phase !== 'chunk' && phase !== 'embed') return

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

  private onExit(job: InternalJob, code: number | null, spawnError?: string): void {
    job.child = null

    if (job.cancelRequested) {
      this.end(job, 'cancelled')
      return
    }

    if (code === 0) {
      this.stepSucceeded(job)
      return
    }

    if (code === BUSY_EXIT_CODE) {
      this.addNote(job, BUSY_EXIT_NOTE)
      this.end(job, 'done')
      return
    }

    job.view.error = spawnError ?? this.errorText(job) ?? `código de saída ${String(code)}`
    this.end(job, 'failed')
  }

  /** O passo atual terminou bem (ou foi pulado): segue para o próximo ou fecha a tarefa. */
  private stepSucceeded(job: InternalJob): void {
    if (job.stepIndex + 1 < job.resolved.steps.length) {
      job.stepIndex += 1
      this.startStep(job)
      return
    }

    const failure =
      this.verifyFailure(job) ??
      (job.embedError !== null
        ? `Os embeddings não foram gerados: ${job.embedError}`.slice(0, MAX_ERROR_LENGTH)
        : null)
    if (failure !== null) {
      job.view.error = failure
      this.end(job, 'failed')
      return
    }
    this.end(job, 'done')
  }

  private verifyFailure(job: InternalJob): string | null {
    if (!this.deps.verify) return null
    try {
      return this.deps.verify(job.resolved)
    } catch (err) {
      console.error(`verificação da tarefa "${job.view.label}" falhou:`, err)
      return null
    }
  }

  /**
   * A mensagem de erro do CLI (`erro: ...`, impressa pelo Rich) pode vir
   * quebrada em várias linhas: usa o último bloco que começa numa linha
   * `erro:`, juntando as linhas seguintes. Sem ele, a última linha não vazia
   * de stderr (ou de stdout).
   */
  private errorText(job: InternalJob): string | null {
    const lines = job.stderrLines
    for (let i = lines.length - 1; i >= 0; i--) {
      if (lines[i].trimStart().startsWith('erro:')) {
        const block = lines
          .slice(i)
          .map((l) => l.trim())
          .filter((l) => l.length > 0)
          .join(' ')
        return block.slice(0, MAX_ERROR_LENGTH)
      }
    }
    const lastStderr = [...lines].reverse().find((l) => l.trim().length > 0) ?? null
    const last = lastStderr ?? job.lastStdoutLine
    return last !== null ? last.slice(0, MAX_ERROR_LENGTH) : null
  }

  private end(job: InternalJob, state: JobState): void {
    this.removeFromActive(job)
    this.finish(job, state)
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

/**
 * Quebra um stream em linhas. Decodifica UTF-8 com `StringDecoder` (um
 * caractere multibyte partido entre dois pedaços não vira lixo) e aceita
 * `\r\n`, `\n` e `\r` sozinho como fim de linha. A última linha parcial de
 * cada pedaço espera o próximo; um `\r` no fim de um pedaço também espera,
 * porque pode ser a metade de um `\r\n`.
 */
export function createLineBuffer(emit: (line: string) => void) {
  const decoder = new StringDecoder('utf8')
  let pending = ''

  function drain(text: string): void {
    pending += text
    let held = ''
    if (pending.endsWith('\r')) {
      held = '\r'
      pending = pending.slice(0, -1)
    }
    const lines = pending.split(/\r\n|\n|\r/)
    pending = (lines.pop() ?? '') + held
    for (const line of lines) emit(line)
  }

  return {
    push(chunk: Buffer | string): void {
      drain(typeof chunk === 'string' ? chunk : decoder.write(chunk))
    },
    flush(): void {
      drain(decoder.end())
      let rest = pending
      pending = ''
      if (rest.endsWith('\r')) rest = rest.slice(0, -1)
      if (rest.length > 0) emit(rest)
    },
  }
}

function spawnErrorText(err: NodeJS.ErrnoException, cmd: string, cwd: string): string {
  if (err.code === 'ENOENT') {
    // Node também dá ENOENT quando é a pasta de trabalho que sumiu.
    if (!fs.existsSync(cwd)) return `Pasta não encontrada: ${cwd}`
    return `Comando não encontrado: ${cmd}`
  }
  return `Não foi possível iniciar ${cmd}: ${err.message}`
}

/**
 * `spawn` real, sem shell (obrigatório - ver global-constraints.md).
 * `'ragx'` resolve para o caminho absoluto achado por `ragxCommand()` (fora
 * do PATH do app aberto pelo menu Iniciar).
 *
 * - `cwd` `null` (comandos globais: `init`, `mcp install`, `project
 *   unregister`, `docker`) roda na pasta do usuário, nunca no cwd do Electron.
 * - `COLUMNS=500`: fora de um TTY o Rich quebra a mensagem de erro em 80
 *   colunas, o que picotava o texto mostrado na tarefa.
 *
 * Sem timeout, de propósito: indexação de projeto grande roda por muito
 * tempo de forma legítima, e toda tarefa da fila já é cancelável por
 * `JobQueue.cancel()` - um timeout aqui só mataria indexações lentas e
 * legítimas sem dar nenhuma proteção que `cancel()` já não dê.
 */
export function defaultSpawn(): SpawnFn {
  return (cmd, args, cwd) => {
    const resolvedCmd = cmd === 'ragx' ? ragxCommand() : cmd
    const workDir = cwd ?? os.homedir()
    const child = nodeSpawn(resolvedCmd, args, {
      cwd: workDir,
      windowsHide: true,
      env: { ...process.env, COLUMNS: '500' },
    })

    let outCb: (line: string) => void = () => {}
    let errCb: (line: string) => void = () => {}
    let exitCb: ExitCallback = () => {}
    // Node emite `error` e depois ainda `close` quando o processo nem chega
    // a nascer (ex.: ENOENT) - sem essa guarda, `exitCb` seria chamado duas
    // vezes para a mesma tarefa.
    let settled = false

    const outBuf = createLineBuffer((l) => outCb(l))
    const errBuf = createLineBuffer((l) => errCb(l))

    child.stdout?.on('data', (chunk: Buffer) => outBuf.push(chunk))
    child.stderr?.on('data', (chunk: Buffer) => errBuf.push(chunk))

    // `close` (não `exit`): garante que os streams de stdio já terminaram de
    // entregar dados antes de soltar o resto do buffer e avisar quem chamou.
    child.on('close', (code) => {
      if (settled) return
      settled = true
      outBuf.flush()
      errBuf.flush()
      exitCb(code)
    })
    child.on('error', (err: NodeJS.ErrnoException) => {
      if (settled) return
      settled = true
      outBuf.flush()
      errBuf.flush()
      exitCb(null, spawnErrorText(err, resolvedCmd, workDir))
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

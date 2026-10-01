import fs from 'node:fs'
import path from 'node:path'
import { nodeTailFs, type TailFs } from './activity'
import type { SavingsDay, SavingsSeries, TelemetrySummary } from './types'

interface LogLine {
  ts: string
  tool: string
  ms: number
  project: string
  tokens_delivered?: number
  baseline_tokens?: number
  // Log v2 do servidor MCP (RAGX-0156). Linha antiga não os tem, e continua válida.
  v?: number
  ok?: boolean
  err_code?: string
  resp_chars?: number
  resp_tokens?: number
}

/** Dias no gráfico de economia do detalhe do projeto. */
export const SAVINGS_DAYS = 14

function localDate(ms: number): string {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Série vazia com um dia zerado para cada um dos últimos `days` dias (hoje incluso). */
export function emptySavings(nowMs: number, days = SAVINGS_DAYS): SavingsSeries {
  const out: SavingsDay[] = []
  const today = new Date(nowMs)
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i, 12)
    out.push({ date: localDate(d.getTime()), baseline: 0, delivered: 0, calls: 0 })
  }
  return { days: out, baseline: 0, delivered: 0, calls: 0 }
}

/**
 * Soma no dia (local) da chamada. Só conta a linha que tem AS DUAS medidas:
 * uma linha antiga, sem `baseline_tokens`, entraria como "100% de economia".
 */
function addSavings(series: SavingsSeries, byDate: Map<string, SavingsDay>, entry: LogLine, entryMs: number): void {
  if (entry.tool !== 'build_context') return
  const { tokens_delivered: delivered, baseline_tokens: baseline } = entry
  if (typeof delivered !== 'number' || typeof baseline !== 'number') return
  const day = byDate.get(localDate(entryMs))
  if (day === undefined) return // fora da janela
  day.baseline += baseline
  day.delivered += delivered
  day.calls += 1
  series.baseline += baseline
  series.delivered += delivered
  series.calls += 1
}

/**
 * A leitura COMPLETA, sem estado: relê o `mcp.jsonl` inteiro a cada chamada. Fica como a referência de
 * exatidão da leitura incremental (`createTelemetryTail`) e para a medição do ganho (RAGX-0174); o painel
 * usa a incremental.
 */
export function readTelemetryFull(projectPath: string, sinceHours: number): TelemetrySummary {
  const logPath = path.join(projectPath, '.ragx', 'logs', 'mcp.jsonl')
  if (!fs.existsSync(logPath)) {
    return { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null, savings: emptySavings(Date.now()) }
  }

  const cutoff = Date.now() - sinceHours * 3600 * 1000
  const byTool = new Map<string, number>()
  let tokensDelivered = 0
  let totalCalls = 0
  // Maior `ts` visto, independente da janela `sinceHours` (ver `lastCallAt`
  // abaixo) - por isso rastreado fora do `continue` que filtra a janela.
  let lastCallAt: string | null = null
  let lastCallAtMs = -Infinity

  const savings = emptySavings(Date.now())
  const byDate = new Map(savings.days.map((d) => [d.date, d]))

  const raw = fs.readFileSync(logPath, 'utf-8')
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue
    let entry: LogLine
    try {
      entry = JSON.parse(line)
    } catch {
      continue // linha corrompida (escrita concorrente truncada) - ignora, nao quebra o painel
    }
    // `JSON.parse` aceita `null`, `123`, `"texto"` etc. como JSON valido, mas
    // essas linhas nao sao um LogLine - acessar entry.tool/.ts quebraria (ou
    // poluiria a agregacao com `undefined`). Trata como corrompida.
    if (typeof entry !== 'object' || entry === null) continue

    const entryMs = new Date(entry.ts).getTime()
    if (!Number.isNaN(entryMs) && entryMs > lastCallAtMs) {
      lastCallAtMs = entryMs
      lastCallAt = entry.ts
    }

    if (!Number.isNaN(entryMs)) addSavings(savings, byDate, entry, entryMs)

    if (entryMs < cutoff) continue

    totalCalls += 1
    byTool.set(entry.tool, (byTool.get(entry.tool) ?? 0) + 1)
    if (typeof entry.tokens_delivered === 'number') {
      tokensDelivered += entry.tokens_delivered
    }
  }

  return {
    callsByTool: [...byTool.entries()].map(([tool, count]) => ({ tool, count })),
    totalCalls,
    tokensDelivered,
    lastCallAt,
    savings,
  }
}

// -- leitura incremental (RAGX-0174) ------------------------------------------

/** Na primeira leitura de um log só o fim dele: ~14 dias de uso normal, e um arquivo de meses não é lido inteiro. */
export const TELEMETRY_INITIAL_TAIL_BYTES = 4 * 1024 * 1024
/** Dias de buckets guardados (a série do gráfico mostra `SAVINGS_DAYS`; a folga cobre a virada do dia). */
const KEEP_DAYS = SAVINGS_DAYS + 2

interface DayBucket {
  baseline: number
  delivered: number
  calls: number
}

interface WindowEntry {
  ms: number
  tool: string
  tokens: number
}

interface FileState {
  offset: number
  signature: string | null
  windowHours: number
  lastCallAtMs: number
  lastCallAt: string | null
  days: Map<string, DayBucket>
  window: WindowEntry[]
  /** Linhas sem `ts` válido: a leitura completa as conta SEMPRE (`NaN < cutoff` é falso), e nunca saem da janela. */
  undated: { byTool: Map<string, number>; calls: number; tokens: number }
  summary: TelemetrySummary | null
  validUntil: number
}

function freshState(windowHours: number): FileState {
  return {
    offset: 0,
    signature: null,
    windowHours,
    lastCallAtMs: -Infinity,
    lastCallAt: null,
    days: new Map(),
    window: [],
    undated: { byTool: new Map(), calls: 0, tokens: 0 },
    summary: null,
    validUntil: -Infinity,
  }
}

function ingest(state: FileState, text: string, nowMs: number): void {
  const cutoff = nowMs - state.windowHours * 3600 * 1000
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    let entry: LogLine
    try {
      entry = JSON.parse(line)
    } catch {
      continue
    }
    if (typeof entry !== 'object' || entry === null) continue

    const entryMs = new Date(entry.ts).getTime()
    const tokens = typeof entry.tokens_delivered === 'number' ? entry.tokens_delivered : 0
    if (Number.isNaN(entryMs)) {
      state.undated.calls += 1
      state.undated.byTool.set(entry.tool, (state.undated.byTool.get(entry.tool) ?? 0) + 1)
      state.undated.tokens += tokens
      continue
    }
    if (entryMs > state.lastCallAtMs) {
      state.lastCallAtMs = entryMs
      state.lastCallAt = entry.ts
    }
    if (entry.tool === 'build_context' && typeof entry.tokens_delivered === 'number' && typeof entry.baseline_tokens === 'number') {
      const key = localDate(entryMs)
      const day = state.days.get(key) ?? { baseline: 0, delivered: 0, calls: 0 }
      day.baseline += entry.baseline_tokens
      day.delivered += entry.tokens_delivered
      day.calls += 1
      state.days.set(key, day)
    }
    if (entryMs >= cutoff) state.window.push({ ms: entryMs, tool: entry.tool, tokens })
  }
}

function summarizeState(state: FileState, sinceHours: number, nowMs: number): TelemetrySummary {
  const cutoff = nowMs - sinceHours * 3600 * 1000
  state.window = state.window.filter((e) => e.ms >= cutoff)
  const byTool = new Map(state.undated.byTool)
  let totalCalls = state.undated.calls
  let tokensDelivered = state.undated.tokens
  for (const e of state.window) {
    totalCalls += 1
    byTool.set(e.tool, (byTool.get(e.tool) ?? 0) + 1)
    tokensDelivered += e.tokens
  }

  const savings = emptySavings(nowMs)
  for (const day of savings.days) {
    const b = state.days.get(day.date)
    if (b === undefined) continue
    day.baseline = b.baseline
    day.delivered = b.delivered
    day.calls = b.calls
    savings.baseline += b.baseline
    savings.delivered += b.delivered
    savings.calls += b.calls
  }
  // dias fora da janela (mais velhos que KEEP_DAYS) saem da memória
  const today = new Date(nowMs)
  const limit = localDate(new Date(today.getFullYear(), today.getMonth(), today.getDate() - KEEP_DAYS, 12).getTime())
  for (const key of state.days.keys()) if (key < limit) state.days.delete(key)

  // até quando este resumo vale sem reler nada: a entrada mais velha da janela sai, ou o dia vira
  const midnight = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1).getTime()
  let firstExit = Infinity
  for (const e of state.window) firstExit = Math.min(firstExit, e.ms + sinceHours * 3600 * 1000)
  state.validUntil = Math.min(midnight, firstExit)

  return {
    callsByTool: [...byTool.entries()].map(([tool, count]) => ({ tool, count })),
    totalCalls,
    tokensDelivered,
    lastCallAt: state.lastCallAt,
    savings,
  }
}

export interface TelemetryTail {
  read: (projectPath: string, sinceHours: number) => TelemetrySummary
}

/** Os bytes `[start, end)`; sem `readBytes` na `TailFs`, decodifica e recodifica o texto de `read`. */
function readChunk(io: TailFs, file: string, start: number, end: number): Buffer {
  if (io.readBytes) return io.readBytes(file, start, end)
  return Buffer.from(io.read(file, start, end), 'utf8')
}

/**
 * A telemetria de um projeto lida de forma INCREMENTAL (RAGX-0174): o painel relia o `mcp.jsonl` inteiro, de
 * cada projeto, a cada snapshot (5 s). Aqui cada arquivo tem um deslocamento: sem crescimento é um `stat`
 * (e o MESMO objeto de volta, que a RAGX-0175 usa para não re-renderizar); com crescimento só lê o que foi
 * acrescentado, até a última quebra de linha (a linha parcial espera a volta). A primeira leitura pega só o
 * fim do arquivo (4 MB) e, se ele for menor que isso, também o `mcp.jsonl.1` da rotação. Arquivo menor que o
 * deslocamento, ou com outra assinatura (`ino` + `birthtimeMs`), é outro arquivo: zera e relê.
 * O resultado é idêntico ao de `readTelemetryFull` para o mesmo arquivo.
 */
export function createTelemetryTail(io: TailFs = nodeTailFs, now: () => number = Date.now): TelemetryTail {
  const states = new Map<string, FileState>()

  return {
    read(projectPath, sinceHours) {
      const logPath = path.join(projectPath, '.ragx', 'logs', 'mcp.jsonl')
      const nowMs = now()
      const size = io.size(logPath)
      if (size === null) {
        states.delete(logPath)
        return { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null, savings: emptySavings(nowMs) }
      }
      const signature = io.signature?.(logPath) ?? null
      let state = states.get(logPath)
      if (state && (size < state.offset || signature !== state.signature || sinceHours > state.windowHours)) {
        state = undefined // truncado, rotacionado ou uma janela maior que a guardada: outro arquivo
      }
      let grew = false
      if (!state) {
        state = freshState(sinceHours)
        state.signature = signature
        let start = 0
        if (size > TELEMETRY_INITIAL_TAIL_BYTES) {
          start = size - TELEMETRY_INITIAL_TAIL_BYTES
        } else {
          const rotated = io.size(`${logPath}.1`)
          if (rotated !== null && rotated > 0) {
            const old = readChunk(io, `${logPath}.1`, 0, rotated)
            const lastOldNl = old.lastIndexOf(0x0a)
            if (lastOldNl >= 0) ingest(state, old.subarray(0, lastOldNl + 1).toString('utf8'), nowMs)
          }
        }
        let buf = size > start ? readChunk(io, logPath, start, size) : Buffer.alloc(0)
        let skipped = 0
        if (start > 0) {
          const firstNl = buf.indexOf(0x0a) // a primeira linha começa no meio: descarta
          skipped = firstNl < 0 ? buf.length : firstNl + 1
          buf = buf.subarray(skipped)
        }
        const lastNl = buf.lastIndexOf(0x0a)
        const complete = lastNl >= 0 ? buf.subarray(0, lastNl + 1) : Buffer.alloc(0)
        ingest(state, complete.toString('utf8'), nowMs)
        state.offset = start + skipped + complete.length
        grew = true
        states.set(logPath, state)
      } else if (size > state.offset) {
        const buf = readChunk(io, logPath, state.offset, size)
        const lastNl = buf.lastIndexOf(0x0a)
        if (lastNl >= 0) {
          ingest(state, buf.subarray(0, lastNl + 1).toString('utf8'), nowMs)
          state.offset += lastNl + 1
          grew = true
        }
      }
      if (!grew && state.summary !== null && nowMs < state.validUntil && sinceHours === state.windowHours) {
        return state.summary
      }
      state.windowHours = Math.max(state.windowHours, sinceHours)
      state.summary = summarizeState(state, sinceHours, nowMs)
      return state.summary
    },
  }
}

/** A leitura incremental compartilhada do painel (uma por processo). */
const sharedTail = createTelemetryTail()

/** Compatível com o contrato antigo; o painel usa a leitura incremental compartilhada. */
export function readTelemetry(projectPath: string, sinceHours: number): TelemetrySummary {
  return sharedTail.read(projectPath, sinceHours)
}

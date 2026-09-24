import fs from 'node:fs'
import path from 'node:path'
import type { SavingsDay, SavingsSeries, TelemetrySummary } from './types'

interface LogLine {
  ts: string
  tool: string
  ms: number
  project: string
  tokens_delivered?: number
  baseline_tokens?: number
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

export function readTelemetry(projectPath: string, sinceHours: number): TelemetrySummary {
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

import fs from 'node:fs'
import path from 'node:path'
import type { TelemetrySummary } from './types'

interface LogLine {
  ts: string
  tool: string
  ms: number
  project: string
  tokens_delivered?: number
}

export function readTelemetry(projectPath: string, sinceHours: number): TelemetrySummary {
  const logPath = path.join(projectPath, '.ragx', 'logs', 'mcp.jsonl')
  if (!fs.existsSync(logPath)) {
    return { callsByTool: [], totalCalls: 0, tokensDelivered: 0 }
  }

  const cutoff = Date.now() - sinceHours * 3600 * 1000
  const byTool = new Map<string, number>()
  let tokensDelivered = 0
  let totalCalls = 0

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
    if (new Date(entry.ts).getTime() < cutoff) continue

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
  }
}

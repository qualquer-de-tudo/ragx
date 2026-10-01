/**
 * Resumo da medição de consumo do painel (RAGX-0177). Puro: recebe as amostras já lidas do JSONL.
 */
import type { SpawnTotals } from './spawn-counter'

export type PanelState = 'visible' | 'minimized' | 'hidden'
export const PANEL_STATES: readonly PanelState[] = ['visible', 'minimized', 'hidden']

export interface ProcessSample {
  pid: number
  /** `Browser`, `Tab`, `GPU`, `Utility`... */
  type: string
  /** `percentCPUUsage` do Electron, desde a chamada anterior. */
  cpu: number
  workingSetMB: number
  privateMB: number
}

export interface RuntimeSample {
  /** Segundos desde o início da medição. */
  t: number
  state: PanelState
  warmup?: boolean
  processes: ProcessSample[]
  /** Filhos criados desde a amostra anterior, por executável. */
  spawns: SpawnTotals
  /** Duração da última reconstrução do snapshot, em ms. */
  snapshotMs: number | null
  /** Quanto durou coletar e gravar ESTA amostra, em ms. */
  sampleCostMs?: number
  /** Segundos desde a amostra anterior. */
  dt: number
}

export interface PlanStep {
  state: PanelState
  minutes: number
}

/** `"visible:5,minimized:5,hidden:5"` -> passos. Estado desconhecido ou minutos inválidos lançam. */
export function parsePlan(text: string): PlanStep[] {
  const steps: PlanStep[] = []
  for (const part of text.split(',')) {
    const trimmed = part.trim()
    if (!trimmed) continue
    const [rawState, rawMinutes] = trimmed.split(':')
    if (!PANEL_STATES.includes(rawState as PanelState)) {
      throw new Error(`estado desconhecido no plano: ${rawState} (use visible, minimized ou hidden)`)
    }
    const minutes = Number(rawMinutes)
    if (!Number.isFinite(minutes) || minutes <= 0) {
      throw new Error(`minutos inválidos no plano: ${rawMinutes}`)
    }
    steps.push({ state: rawState as PanelState, minutes })
  }
  if (steps.length === 0) throw new Error('plano vazio')
  return steps
}

export interface StateSummary {
  state: PanelState
  samples: number
  seconds: number
  /** RAM total do painel (soma dos processos), em MB. */
  workingSetMB: { mean: number; peak: number }
  privateMB: { mean: number; peak: number }
  /** CPU somada dos processos (convenção do Electron: por núcleo, pode passar de 100). */
  cpuTotal: { mean: number; p95: number }
  cpuByType: Record<string, { mean: number; p95: number }>
  spawnsPerMinute: Record<string, number>
  spawnMsPerMinute: Record<string, number>
  snapshotMsMean: number | null
  sampleCostMsMean: number | null
}

function mean(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((a, b) => a + b, 0) / values.length
}

export function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))
  return sorted[index]
}

const round = (n: number, digits = 1): number => Math.round(n * 10 ** digits) / 10 ** digits

/** Resume por estado, DESCARTANDO as amostras `warmup` (o CPU do Electron é medido desde a chamada anterior). */
export function summarize(samples: RuntimeSample[]): StateSummary[] {
  const out: StateSummary[] = []
  for (const state of PANEL_STATES) {
    const rows = samples.filter((s) => s.state === state && !s.warmup)
    if (rows.length === 0) continue
    const seconds = rows.reduce((a, s) => a + s.dt, 0)
    const minutes = seconds / 60

    const ws = rows.map((s) => s.processes.reduce((a, p) => a + p.workingSetMB, 0))
    const priv = rows.map((s) => s.processes.reduce((a, p) => a + p.privateMB, 0))
    const cpu = rows.map((s) => s.processes.reduce((a, p) => a + p.cpu, 0))

    const types = new Set(rows.flatMap((s) => s.processes.map((p) => p.type)))
    const cpuByType: StateSummary['cpuByType'] = {}
    for (const type of types) {
      const perSample = rows.map((s) => s.processes.filter((p) => p.type === type).reduce((a, p) => a + p.cpu, 0))
      cpuByType[type] = { mean: round(mean(perSample)), p95: round(percentile(perSample, 95)) }
    }

    const spawnCount: Record<string, number> = {}
    const spawnMs: Record<string, number> = {}
    for (const s of rows) {
      for (const [exe, v] of Object.entries(s.spawns)) {
        spawnCount[exe] = (spawnCount[exe] ?? 0) + v.count
        spawnMs[exe] = (spawnMs[exe] ?? 0) + v.ms
      }
    }
    const perMinute = (totals: Record<string, number>): Record<string, number> =>
      Object.fromEntries(Object.entries(totals).map(([k, v]) => [k, round(minutes > 0 ? v / minutes : 0)]))

    const snaps = rows.map((s) => s.snapshotMs).filter((v): v is number => v !== null)
    const costs = rows.map((s) => s.sampleCostMs).filter((v): v is number => v !== undefined)
    out.push({
      state,
      samples: rows.length,
      seconds: round(seconds, 0),
      workingSetMB: { mean: round(mean(ws)), peak: round(Math.max(...ws)) },
      privateMB: { mean: round(mean(priv)), peak: round(Math.max(...priv)) },
      cpuTotal: { mean: round(mean(cpu)), p95: round(percentile(cpu, 95)) },
      cpuByType,
      spawnsPerMinute: perMinute(spawnCount),
      spawnMsPerMinute: perMinute(spawnMs),
      snapshotMsMean: snaps.length ? round(mean(snaps)) : null,
      sampleCostMsMean: costs.length ? round(mean(costs), 2) : null,
    })
  }
  return out
}

/** Linhas JSONL -> amostras. Linha inválida é ignorada (o arquivo pode ter sido cortado no meio). */
export function parseSamples(jsonl: string): RuntimeSample[] {
  const samples: RuntimeSample[] = []
  for (const line of jsonl.split(/\r?\n/)) {
    if (!line.trim()) continue
    try {
      const value = JSON.parse(line) as RuntimeSample
      if (value && typeof value.t === 'number' && PANEL_STATES.includes(value.state)) samples.push(value)
    } catch {
      // linha truncada
    }
  }
  return samples
}

/** Tabela markdown de um resumo (uma linha por estado), para `medicao-runtime.md`. */
export function toMarkdownTable(summaries: StateSummary[]): string {
  const header =
    '| Estado | Amostras | RAM working set (média / pico MB) | RAM privada (média / pico MB) | CPU soma (média / p95) | `git`/min | filhos (ms/min) | snapshot (ms) |\n' +
    '|---|---|---|---|---|---|---|---|'
  const rows = summaries.map((s) => {
    const totalMs = Object.values(s.spawnMsPerMinute).reduce((a, b) => a + b, 0)
    return `| ${s.state} | ${s.samples} | ${s.workingSetMB.mean} / ${s.workingSetMB.peak} | ${s.privateMB.mean} / ${s.privateMB.peak} | ${s.cpuTotal.mean} / ${s.cpuTotal.p95} | ${s.spawnsPerMinute.git ?? 0} | ${round(totalMs, 0)} | ${s.snapshotMsMean ?? '-'} |`
  })
  return [header, ...rows].join('\n')
}

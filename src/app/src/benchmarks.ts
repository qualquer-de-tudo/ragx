import raw from './data/benchmarks.json'

/**
 * Benchmarks públicos do RAGX: o que foi medido, quando, em qual versão e com qual método. A fonte única é
 * `data/benchmarks.json` (o painel o embute: nenhuma chamada de rede); `scripts/gerar_benchmarks.py` gera dele a página
 * `docs/27-benchmarks.md`, e um teste confere que as duas coincidem.
 */

export type Unit = 'tokens' | 'ms' | 's' | 'proc/min'

export interface Snapshot {
  id: string
  version: string
  date: string
  title: string
}

export interface Point {
  snapshot: string
  /** `null` quando a linha de base não existia (por exemplo, "indefinida"). */
  value: number | null
  note?: string
}

export interface Metric {
  id: string
  group: string
  name: string
  detail: string
  unit: Unit
  lowerIsBetter: boolean
  points: Point[]
  goal?: { value: number; met: boolean }
  method: string
  caveat?: string
}

export interface AbRow {
  label: string
  without: string
  with: string
  note: string
}

export interface RetrievalRow {
  model: string
  manual: number
  manualCi: [number, number]
  git: number
  gitCi: [number, number]
  queryMs: number
}

export interface TimelineEntry {
  date: string
  version: string
  title: string
  text: string
  metrics: string[]
}

export interface BenchmarkData {
  schema: number
  updated: string
  environment: string
  intro: string
  snapshots: Snapshot[]
  metrics: Metric[]
  ab: { date: string; title: string; setup: string; verdict: string; rows: AbRow[]; reading: string; method: string }
  retrieval: { title: string; intro: string; date: string; rows: RetrievalRow[]; note: string; method: string }
  timeline: TimelineEntry[]
}

export const benchmarks = raw as unknown as BenchmarkData

const nf = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 })

/** "7.684 tokens", "40 ms", "1,77 s", "4,1 proc/min". Estas medidas nunca passam de duas casas. */
export function formatValue(value: number | null, unit: Unit): string {
  if (value === null) return 'indefinido'
  return `${nf.format(value)} ${unit}`
}

export interface Change {
  before: number | null
  after: number
  /** Variação em % (negativa = caiu). `null` sem linha de base. */
  pct: number | null
  /** A variação é uma melhora, segundo `lowerIsBetter`. */
  better: boolean | null
}

/** Do primeiro ao último ponto da métrica. */
export function changeOf(m: Metric): Change {
  const first = m.points[0]
  const last = m.points[m.points.length - 1]
  const after = last.value ?? 0
  if (first === last || first.value === null || first.value === 0) return { before: first.value, after, pct: null, better: null }
  const pct = ((after - first.value) / first.value) * 100
  return { before: first.value, after, pct, better: m.lowerIsBetter ? pct < 0 : pct > 0 }
}

/** "−62%" ou "+4%", com o sinal de menos tipográfico; vazio sem linha de base. */
export function formatPct(pct: number | null): string {
  if (pct === null) return ''
  const abs = Math.abs(pct)
  const n = abs >= 10 ? Math.round(abs) : Math.round(abs * 10) / 10
  return `${pct < 0 ? '−' : '+'}${nf.format(n)}%`
}

/** "2 de out de 2026", sem depender do fuso: a data vem como AAAA-MM-DD. */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
  return `${d} de ${meses[m - 1]} de ${y}`
}

export function groups(metrics: readonly Metric[]): Array<{ name: string; metrics: Metric[] }> {
  const out: Array<{ name: string; metrics: Metric[] }> = []
  for (const m of metrics) {
    const g = out.find((x) => x.name === m.group)
    if (g) g.metrics.push(m)
    else out.push({ name: m.group, metrics: [m] })
  }
  return out
}

/** Quantas metas medidas foram atingidas, e quantas existem. */
export function goalsMet(metrics: readonly Metric[]): { met: number; total: number } {
  const withGoal = metrics.filter((m) => m.goal)
  return { met: withGoal.filter((m) => m.goal?.met).length, total: withGoal.length }
}

import type { JobKind, ProjectSnapshot } from './types/ragx-bridge'
import type { IndexRun, ProjectStatus } from './projectStatus'
import type { ProjectState } from './state'

/**
 * Saúde do índice com tendência (RAGX-0189). Puro, sem React nem DOM, para poder ir ao processo principal (RAGX-0191).
 * O que existe é o histórico de INDEXAÇÕES (`index_runs`, as 10 mais recentes de `ragx status`), não uma série de
 * cobertura ou de defasagem: a tendência é a dele, e a tela diz isso.
 */

/** Indexações mínimas para falar em tendência. Decisão desta tarefa, não medida: com menos, "poucos dados". */
export const MIN_RUNS_FOR_TREND = 6
/** Quanto a mediana das 3 mais novas precisa passar (ou ficar abaixo, em 1/x) da mediana das anteriores. Decisão desta tarefa, não medida. */
export const TREND_RATIO = 1.5
/** As mais novas comparadas com as anteriores. */
const RECENT_WINDOW = 3

export type HealthLevel = 'ok' | 'warn' | 'bad'

export interface HealthCheck {
  id: 'embeddings' | 'last-run' | 'failing' | 'hooks'
  level: HealthLevel
  text: string
  /** `kind` de `STATE_ACTION` que resolve, quando existe. */
  action: JobKind | null
}

export type TrendDirection = 'slower' | 'steady' | 'faster' | 'few-data' | 'no-duration'

export interface Trend {
  direction: TrendDirection
  /** Mediana de `durationMs` das indexações sem mudança (`indexed === 0`, sem erro); `null` sem amostra. */
  medianNoChangeMs: number | null
  /** Idem, das com mudança (`indexed > 0`, sem erro). */
  medianWithChangeMs: number | null
  /** Falhas nas indexações consideradas. */
  failures: number
  runs: number
  text: string
}

export interface IndexHealth {
  level: HealthLevel
  checks: HealthCheck[]
  trend: Trend
}

const RANK: Record<HealthLevel, number> = { ok: 0, warn: 1, bad: 2 }

export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null
  const v = [...values].sort((a, b) => a - b)
  const mid = Math.floor(v.length / 2)
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2
}

/** Duração de uma indexação: `durationMs` da CLI ou, na falta dela (CLI antiga), `finishedAt - startedAt`. */
export function runDuration(r: IndexRun): number | null {
  if (r.durationMs !== null) return r.durationMs
  if (r.startedAt && r.finishedAt) {
    const d = Date.parse(r.finishedAt) - Date.parse(r.startedAt)
    return d >= 0 ? d : null
  }
  return null
}

function seconds(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`
}

/** `runs` vem do mais novo ao mais antigo (a ordem de `ragx status`). */
export function computeTrend(runs: readonly IndexRun[]): Trend {
  const failures = runs.filter((r) => r.error !== null).length
  const ok = runs.filter((r) => r.error === null)
  const noChange = ok.filter((r) => r.indexed === 0).map(runDuration).filter((d): d is number => d !== null)
  const withChange = ok.filter((r) => r.indexed !== null && r.indexed > 0).map(runDuration).filter((d): d is number => d !== null)
  const base = {
    medianNoChangeMs: median(noChange),
    medianWithChangeMs: median(withChange),
    failures,
    runs: runs.length,
  }
  const durations = runs.map(runDuration)
  if (runs.length > 0 && durations.every((d) => d === null)) {
    return { ...base, direction: 'no-duration', text: 'sem dado de duração' }
  }
  if (runs.length < MIN_RUNS_FOR_TREND) {
    return { ...base, direction: 'few-data', text: `poucos dados para tendência (${runs.length} de ${MIN_RUNS_FOR_TREND} indexações)` }
  }
  const recent = durations.slice(0, RECENT_WINDOW).filter((d): d is number => d !== null)
  const before = durations.slice(RECENT_WINDOW).filter((d): d is number => d !== null)
  const mRecent = median(recent)
  const mBefore = median(before)
  if (mRecent === null || mBefore === null || mBefore === 0) {
    return { ...base, direction: 'few-data', text: `poucos dados para tendência (${runs.length} de ${MIN_RUNS_FOR_TREND} indexações)` }
  }
  const direction: TrendDirection = mRecent > mBefore * TREND_RATIO ? 'slower' : mRecent < mBefore / TREND_RATIO ? 'faster' : 'steady'
  const label = { slower: 'mais lenta', faster: 'mais rápida', steady: 'estável' }[direction]
  return {
    ...base,
    direction,
    text: `${label}: as ${RECENT_WINDOW} mais novas levam ${seconds(mRecent)} contra ${seconds(mBefore)} nas anteriores`,
  }
}

/** Quantas indexações seguidas, da mais nova para trás, falharam. */
function consecutiveFailures(runs: readonly IndexRun[]): number {
  let n = 0
  for (const r of runs) {
    if (r.error === null) break
    n += 1
  }
  return n
}

export function computeIndexHealth(args: {
  project: ProjectSnapshot
  state: ProjectState
  status: ProjectStatus | null
  now?: number
}): IndexHealth {
  const { project, status } = args
  const runs = status?.runs ?? []
  const checks: HealthCheck[] = []

  const pending = project.counts?.pendingEmbeddings ?? null
  if (pending === null) checks.push({ id: 'embeddings', level: 'warn', text: 'Embeddings: sem dado.', action: null })
  else if (pending > 0) checks.push({ id: 'embeddings', level: 'warn', text: `Embeddings pendentes: ${pending} chunk(s).`, action: 'embed' })
  else checks.push({ id: 'embeddings', level: 'ok', text: 'Todos os chunks têm embedding.', action: null })

  if (status === null || runs.length === 0) {
    checks.push({ id: 'last-run', level: 'warn', text: 'Última indexação: sem dado.', action: null })
  } else if (runs[0].error !== null) {
    checks.push({ id: 'last-run', level: 'bad', text: `A última indexação falhou: ${runs[0].error}`, action: null })
  } else {
    checks.push({ id: 'last-run', level: 'ok', text: 'A última indexação terminou sem erro.', action: null })
  }

  const streak = consecutiveFailures(runs)
  if (streak >= 2) checks.push({ id: 'failing', level: 'bad', text: `O índice está falhando: ${streak} indexações seguidas com erro.`, action: null })

  if (project.hooksInstalled === false) {
    checks.push({ id: 'hooks', level: 'warn', text: 'Hooks de git ausentes: o índice só atualiza quando você pede.', action: 'hooks-install' })
  } else if (project.hooksInstalled === null) {
    checks.push({ id: 'hooks', level: 'warn', text: 'Hooks de git: sem dado.', action: null })
  }

  const level = checks.reduce<HealthLevel>((w, c) => (RANK[c.level] > RANK[w] ? c.level : w), 'ok')
  return { level, checks, trend: computeTrend(runs) }
}

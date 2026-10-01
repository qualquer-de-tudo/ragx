import { describe, expect, it } from 'vitest'
import { MIN_RUNS_FOR_TREND, TREND_RATIO, computeIndexHealth, computeTrend, median, runDuration } from '../indexHealth'
import { parseProjectStatus, parseRunsPage, type IndexRun, type ProjectStatus } from '../projectStatus'
import { snap } from '../test/snap'

let n = 0
function run(over: Partial<IndexRun> = {}): IndexRun {
  n += 1
  return {
    key: `r${n}`, startedAt: '2026-10-01T10:00:00Z', finishedAt: '2026-10-01T10:00:02Z', mode: 'incremental', source: 'cli',
    branch: 'main', commit: 'c1', indexed: 0, durationMs: 2000, filesSeen: 10, blocked: 0, embedded: 0, error: null, ...over,
  }
}
const status = (runs: IndexRun[]): ProjectStatus => ({ freshness: { state: 'fresh', reasons: [] }, runs })
const health = (over: Parameters<typeof snap>[0] = {}, runs: IndexRun[] = [run()]) =>
  computeIndexHealth({ project: snap(over), state: 'ok', status: status(runs) })

describe('computeIndexHealth: checagens', () => {
  it('tudo certo é ok', () => {
    const h = health()
    expect(h.level).toBe('ok')
    expect(h.checks.every((c) => c.level === 'ok')).toBe(true)
  })

  it('embeddings pendentes: warn com ação embed', () => {
    const h = health({ counts: { documents: 1, chunks: 10, embeddings: 4, pendingEmbeddings: 6 } })
    expect(h.level).toBe('warn')
    expect(h.checks.find((c) => c.id === 'embeddings')).toMatchObject({ level: 'warn', action: 'embed' })
  })

  it('erro na última indexação: bad', () => {
    const h = health({}, [run({ error: 'embedder fora' }), run()])
    expect(h.level).toBe('bad')
    expect(h.checks.find((c) => c.id === 'last-run')).toMatchObject({ level: 'bad' })
    expect(h.checks.find((c) => c.id === 'failing')).toBeUndefined() // só 1 seguida
  })

  it('dois erros seguidos: "está falhando"', () => {
    const h = health({}, [run({ error: 'x' }), run({ error: 'y' }), run()])
    expect(h.checks.find((c) => c.id === 'failing')?.text).toMatch(/está falhando: 2 indexações seguidas/)
    expect(h.level).toBe('bad')
  })

  it('hooks ausentes: warn com ação hooks-install; sem dado de hooks diz "sem dado"', () => {
    expect(health({ hooksInstalled: false }).checks.find((c) => c.id === 'hooks')).toMatchObject({ level: 'warn', action: 'hooks-install' })
    expect(health({ hooksInstalled: null }).checks.find((c) => c.id === 'hooks')?.text).toContain('sem dado')
  })

  it('dado ausente nunca diz ok: sem status, sem counts', () => {
    const h = computeIndexHealth({ project: snap({ counts: null }), state: 'ok', status: null })
    expect(h.checks.find((c) => c.id === 'last-run')).toMatchObject({ level: 'warn', text: expect.stringContaining('sem dado') })
    expect(h.checks.find((c) => c.id === 'embeddings')).toMatchObject({ level: 'warn', text: expect.stringContaining('sem dado') })
    expect(h.level).toBe('warn')
  })
})

describe('computeTrend', () => {
  const durs = (ms: number[]) => ms.map((d) => run({ durationMs: d }))

  it('constantes nomeadas', () => {
    expect(MIN_RUNS_FOR_TREND).toBe(6)
    expect(TREND_RATIO).toBe(1.5)
  })

  it('as 3 mais novas acima de 1,5x a mediana das anteriores: mais lenta', () => {
    // do mais novo ao mais antigo: 3 novas de 20 s e 7 anteriores de 2 s
    expect(computeTrend(durs([20000, 20000, 20000, 2000, 2000, 2000, 2000, 2000, 2000, 2000])).direction).toBe('slower')
  })

  it('abaixo de 1/1,5: mais rápida; entre os limites: estável', () => {
    expect(computeTrend(durs([1000, 1000, 1000, 6000, 6000, 6000, 6000, 6000, 6000, 6000])).direction).toBe('faster')
    expect(computeTrend(durs([2400, 2400, 2400, 2000, 2000, 2000, 2000, 2000, 2000, 2000])).direction).toBe('steady')
  })

  it('exatamente no limite é estável (a comparação é estrita)', () => {
    expect(computeTrend(durs([3000, 3000, 3000, 2000, 2000, 2000, 2000, 2000, 2000, 2000])).direction).toBe('steady')
  })

  it('5 indexações: poucos dados, com a contagem', () => {
    const t = computeTrend(durs([1, 2, 3, 4, 5]))
    expect(t.direction).toBe('few-data')
    expect(t.text).toBe('poucos dados para tendência (5 de 6 indexações)')
  })

  it('medianas separam sem mudança e com mudança, e falhas ficam fora delas', () => {
    const t = computeTrend([
      run({ indexed: 0, durationMs: 4000 }), run({ indexed: 0, durationMs: 2000 }), run({ indexed: 5, durationMs: 9000 }),
      run({ indexed: 3, durationMs: 1000, error: 'x' }), run({ indexed: 0, durationMs: 6000 }), run({ indexed: 2, durationMs: 3000 }),
    ])
    expect(t.medianNoChangeMs).toBe(4000)
    expect(t.medianWithChangeMs).toBe(6000)
    expect(t.failures).toBe(1)
  })

  it('duração ausente em todas: "sem dado de duração" (e a duração cai para finishedAt - startedAt quando dá)', () => {
    const sem = [1, 2, 3].map(() => run({ durationMs: null, startedAt: null, finishedAt: null }))
    expect(computeTrend(sem)).toMatchObject({ direction: 'no-duration', text: 'sem dado de duração' })
    expect(runDuration(run({ durationMs: null, startedAt: '2026-10-01T10:00:00Z', finishedAt: '2026-10-01T10:00:05Z' }))).toBe(5000)
  })

  it('median', () => {
    expect(median([])).toBeNull()
    expect(median([3, 1, 2])).toBe(2)
    expect(median([1, 2, 3, 4])).toBe(2.5)
  })
})

describe('parseRun: campos novos (RAGX-0189)', () => {
  const raw = { id: 7, started_at: '2026-10-01T10:00:00Z', finished_at: '2026-10-01T10:00:02Z', indexed: 1, duration_ms: 1570, files_seen: 761, blocked: 23, embedded: 1, error: null }

  it('lê duration_ms, files_seen, blocked e embedded', () => {
    const [r] = parseProjectStatus({ initialized: true, recent_runs: [raw] })!.runs
    expect(r).toMatchObject({ durationMs: 1570, filesSeen: 761, blocked: 23, embedded: 1 })
  })

  it('ausente ou inválido vira null', () => {
    const [r] = parseRunsPage({ runs: [{ id: 1, duration_ms: -5, files_seen: 'muitos', blocked: 1.5 }], total: 1 }, 0)!.runs
    expect(r).toMatchObject({ durationMs: null, filesSeen: null, blocked: null, embedded: null })
  })
})

import { describe, expect, it } from 'vitest'
import { benchmarks, changeOf, formatDate, formatPct, formatValue, goalsMet, groups, type Metric } from '../benchmarks'

const metric = (over: Partial<Metric> = {}): Metric => ({
  id: 'm', group: 'g', name: 'M', detail: 'd', unit: 'tokens', lowerIsBetter: true, method: 'x',
  points: [{ snapshot: 'a', value: 100 }, { snapshot: 'b', value: 40 }], ...over,
})

describe('benchmarks: contas', () => {
  it('variação do primeiro ao último ponto, e se é melhora conforme o sentido da métrica', () => {
    expect(changeOf(metric())).toEqual({ before: 100, after: 40, pct: -60, better: true })
    expect(changeOf(metric({ lowerIsBetter: false })).better).toBe(false)
    expect(changeOf(metric({ points: [{ snapshot: 'a', value: 10 }, { snapshot: 'b', value: 15 }], lowerIsBetter: false })).better).toBe(true)
  })

  it('sem linha de base, ou com um ponto só, não inventa variação', () => {
    expect(changeOf(metric({ points: [{ snapshot: 'a', value: null }, { snapshot: 'b', value: 1.4 }] }))).toEqual({ before: null, after: 1.4, pct: null, better: null })
    expect(changeOf(metric({ points: [{ snapshot: 'a', value: 5 }] })).pct).toBeNull()
  })

  it('formata valor, porcentagem e data em português, sem depender do fuso', () => {
    expect(formatValue(7684, 'tokens')).toBe('7.684 tokens')
    expect(formatValue(1.77, 's')).toBe('1,77 s')
    expect(formatValue(null, 'ms')).toBe('indefinido')
    expect(formatPct(-61.5)).toBe('−62%')
    expect(formatPct(-0.8)).toBe('−0,8%')
    expect(formatPct(4)).toBe('+4%')
    expect(formatPct(null)).toBe('')
    expect(formatDate('2026-10-02')).toBe('2 de out de 2026')
  })

  it('agrupa na ordem em que aparecem e conta metas atingidas', () => {
    const ms = [metric({ id: '1', group: 'A', goal: { value: 1, met: true } }), metric({ id: '2', group: 'B' }), metric({ id: '3', group: 'A', goal: { value: 1, met: false } })]
    expect(groups(ms).map((g) => [g.name, g.metrics.map((m) => m.id)])).toEqual([['A', ['1', '3']], ['B', ['2']]])
    expect(goalsMet(ms)).toEqual({ met: 1, total: 2 })
  })
})

describe('benchmarks: os dados publicados', () => {
  const snapshotIds = new Set(benchmarks.snapshots.map((s) => s.id))

  it('toda métrica aponta para snapshots que existem, tem método e unidade conhecida', () => {
    for (const m of benchmarks.metrics) {
      expect(m.method.length, m.id).toBeGreaterThan(10)
      expect(['tokens', 'ms', 's', 'proc/min'], m.id).toContain(m.unit)
      expect(m.points.length, m.id).toBeGreaterThanOrEqual(2)
      for (const p of m.points) expect(snapshotIds.has(p.snapshot), `${m.id}:${p.snapshot}`).toBe(true)
    }
  })

  it('a meta marcada como atingida é coerente com o último valor medido', () => {
    for (const m of benchmarks.metrics) {
      if (!m.goal) continue
      const { after } = changeOf(m)
      const ok = m.lowerIsBetter ? after <= m.goal.value : after >= m.goal.value
      expect(ok, `${m.id}: ${after} contra meta ${m.goal.value}`).toBe(m.goal.met)
    }
  })

  it('a meta não atingida traz o porquê, e métricas que melhoraram não escondem o que piorou', () => {
    for (const m of benchmarks.metrics) if (m.goal && !m.goal.met) expect(m.caveat, m.id).toBeTruthy()
    expect(benchmarks.ab.verdict.toLowerCase()).toContain('inconclusivo')
  })

  it('a linha do tempo só cita métricas que existem e está ordenada por data', () => {
    const ids = new Set(benchmarks.metrics.map((m) => m.id))
    for (const e of benchmarks.timeline) for (const id of e.metrics) expect(ids.has(id), id).toBe(true)
    const datas = benchmarks.timeline.map((e) => e.date)
    expect([...datas].sort()).toEqual(datas)
  })
})

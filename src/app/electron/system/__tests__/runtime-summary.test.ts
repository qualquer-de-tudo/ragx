import { describe, expect, it } from 'vitest'
import { parsePlan, parseSamples, percentile, summarize, toMarkdownTable, type RuntimeSample } from '../runtime-summary'

const sample = (over: Partial<RuntimeSample> & Pick<RuntimeSample, 'state'>): RuntimeSample => ({
  t: 0,
  dt: 5,
  processes: [],
  spawns: {},
  snapshotMs: null,
  ...over,
})

describe('parsePlan', () => {
  it('lê estados e minutos', () => {
    expect(parsePlan('visible:5,minimized:5,hidden:2.5')).toEqual([
      { state: 'visible', minutes: 5 },
      { state: 'minimized', minutes: 5 },
      { state: 'hidden', minutes: 2.5 },
    ])
  })

  it('recusa estado desconhecido, minutos inválidos e plano vazio', () => {
    expect(() => parsePlan('fullscreen:5')).toThrow(/estado desconhecido/)
    expect(() => parsePlan('visible:0')).toThrow(/minutos inválidos/)
    expect(() => parsePlan('visible:abc')).toThrow(/minutos inválidos/)
    expect(() => parsePlan('visible:-1')).toThrow(/minutos inválidos/)
    expect(() => parsePlan('')).toThrow(/plano vazio/)
  })
})

describe('percentile', () => {
  it('p95 de 20 valores é o 19º', () => {
    const v = Array.from({ length: 20 }, (_, i) => i + 1)
    expect(percentile(v, 95)).toBe(19)
    expect(percentile([], 95)).toBe(0)
    expect(percentile([7], 95)).toBe(7)
  })
})

describe('summarize', () => {
  const proc = (type: string, cpu: number, ws: number, priv: number) => ({ pid: 1, type, cpu, workingSetMB: ws, privateMB: priv })

  it('descarta o `warmup` e calcula média e pico da RAM e do CPU por estado', () => {
    const rows = [
      sample({ state: 'visible', warmup: true, processes: [proc('Browser', 99, 999, 999)] }),
      sample({ state: 'visible', processes: [proc('Browser', 2, 100, 50), proc('Tab', 8, 200, 150)] }),
      sample({ state: 'visible', processes: [proc('Browser', 4, 100, 50), proc('Tab', 16, 300, 150)] }),
    ]
    const [v] = summarize(rows)
    expect(v.samples).toBe(2)
    expect(v.workingSetMB).toEqual({ mean: 350, peak: 400 })
    expect(v.privateMB).toEqual({ mean: 200, peak: 200 })
    expect(v.cpuTotal).toEqual({ mean: 15, p95: 20 })
    expect(v.cpuByType.Tab).toEqual({ mean: 12, p95: 16 })
    expect(v.cpuByType.Browser).toEqual({ mean: 3, p95: 4 })
  })

  it('filhos por minuto: soma das contagens dividida pelos minutos de amostra', () => {
    // 12 amostras de 5 s = 1 minuto; 24 `git` por amostra = 288/min (o número da auditoria era ~290)
    const rows = Array.from({ length: 12 }, () =>
      sample({ state: 'visible', spawns: { git: { count: 24, ms: 1200 }, docker: { count: 0, ms: 0 } }, snapshotMs: 400 }),
    )
    const [v] = summarize(rows)
    expect(v.seconds).toBe(60)
    expect(v.spawnsPerMinute.git).toBe(288)
    expect(v.spawnMsPerMinute.git).toBe(14_400)
    expect(v.snapshotMsMean).toBe(400)
  })

  it('separa os estados e só devolve os que têm amostras', () => {
    const out = summarize([sample({ state: 'minimized' }), sample({ state: 'hidden' }), sample({ state: 'hidden' })])
    expect(out.map((s) => [s.state, s.samples])).toEqual([
      ['minimized', 1],
      ['hidden', 2],
    ])
  })

  it('o custo médio do amostrador sai do campo `sampleCostMs`', () => {
    const [v] = summarize([
      sample({ state: 'visible', sampleCostMs: 1 }),
      sample({ state: 'visible', sampleCostMs: 3 }),
      sample({ state: 'visible' }),
    ])
    expect(v.sampleCostMsMean).toBe(2)
  })
})

describe('parseSamples e toMarkdownTable', () => {
  it('ignora linha inválida ou truncada', () => {
    const ok = JSON.stringify(sample({ state: 'visible' }))
    const out = parseSamples(`${ok}\nnão é json\n{"t":1,"state":"visible"\n\n${ok}\n`)
    expect(out).toHaveLength(2)
  })

  it('a tabela tem uma linha por estado', () => {
    const md = toMarkdownTable(summarize([sample({ state: 'visible' }), sample({ state: 'hidden' })]))
    expect(md.split('\n')).toHaveLength(4)
    expect(md).toContain('| visible |')
    expect(md).toContain('| hidden |')
  })
})

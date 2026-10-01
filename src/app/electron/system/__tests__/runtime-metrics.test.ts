import { describe, expect, it, vi } from 'vitest'
import { createRuntimeSampler, metricsFileFromEnv, SAMPLE_INTERVAL_MS, type AppMetric } from '../runtime-metrics'
import type { PanelState, RuntimeSample } from '../runtime-summary'
import type { SpawnTotals } from '../spawn-counter'

const metric = (pid: number, type: string, cpu: number, workingSetKB: number, privateKB: number): AppMetric => ({
  pid,
  type,
  cpu: { percentCPUUsage: cpu },
  memory: { workingSetSize: workingSetKB, privateBytes: privateKB },
})

function setup() {
  let clock = 1_000_000
  let state: PanelState = 'visible'
  let spawns: SpawnTotals = {}
  const lines: string[] = []
  let metrics: AppMetric[] = [metric(1, 'Browser', 2.5, 102_400, 51_200), metric(2, 'Tab', 10.123, 204_800, 153_600)]
  let handler: (() => void) | null = null
  const cleared = vi.fn()
  const sampler = createRuntimeSampler({
    getAppMetrics: () => metrics,
    getState: () => state,
    spawns: () => spawns,
    getSnapshotMs: () => 312,
    now: () => clock,
    write: (l) => lines.push(l),
    setInterval: (fn) => {
      handler = fn
      return 'h'
    },
    clearInterval: cleared,
  })
  return {
    sampler,
    lines,
    cleared,
    tick: () => handler?.(),
    advance: (ms: number) => (clock += ms),
    setState: (s: PanelState) => (state = s),
    setSpawns: (s: SpawnTotals) => (spawns = s),
    setMetrics: (m: AppMetric[]) => (metrics = m),
    parsed: (): RuntimeSample[] => lines.map((l) => JSON.parse(l) as RuntimeSample),
  }
}

describe('createRuntimeSampler', () => {
  it('a primeira amostra é `warmup` e as seguintes não', () => {
    const s = setup()
    s.sampler.start()
    s.advance(SAMPLE_INTERVAL_MS)
    s.tick()
    const [a, b] = s.parsed()
    expect(a.warmup).toBe(true)
    expect(b.warmup).toBeUndefined()
  })

  it('converte KB do Electron em MB e arredonda o CPU', () => {
    const s = setup()
    s.sampler.start()
    const [a] = s.parsed()
    expect(a.processes).toEqual([
      { pid: 1, type: 'Browser', cpu: 2.5, workingSetMB: 100, privateMB: 50 },
      { pid: 2, type: 'Tab', cpu: 10.12, workingSetMB: 200, privateMB: 150 },
    ])
    expect(a.snapshotMs).toBe(312)
  })

  it('registra o estado de cada momento e o intervalo entre amostras', () => {
    const s = setup()
    s.sampler.start()
    s.setState('minimized')
    s.advance(5000)
    s.tick()
    s.setState('hidden')
    s.advance(5000)
    s.tick()
    expect(s.parsed().map((x) => x.state)).toEqual(['visible', 'minimized', 'hidden'])
    expect(s.parsed().map((x) => x.dt)).toEqual([0, 5, 5])
    expect(s.parsed().map((x) => x.t)).toEqual([0, 5, 10])
  })

  it('traz só os filhos criados DESDE a amostra anterior, por executável', () => {
    const s = setup()
    s.sampler.start()
    s.setSpawns({ git: { count: 24, ms: 1200 } })
    s.advance(5000)
    s.tick()
    s.setSpawns({ git: { count: 36, ms: 1900 }, docker: { count: 1, ms: 500 } })
    s.advance(5000)
    s.tick()
    const [, b, c] = s.parsed()
    expect(b.spawns).toEqual({ git: { count: 24, ms: 1200 } })
    expect(c.spawns).toEqual({ git: { count: 12, ms: 700 }, docker: { count: 1, ms: 500 } })
  })

  it('o custo da amostra anterior vai na linha seguinte', () => {
    const s = setup()
    s.sampler.start()
    s.advance(5000)
    s.tick()
    const [a, b] = s.parsed()
    expect(a.sampleCostMs).toBeUndefined()
    expect(b.sampleCostMs).toBe(0) // o relógio simulado não anda dentro da amostra
  })

  it('stop() encerra o intervalo e start() duas vezes não cria dois', () => {
    const s = setup()
    s.sampler.start()
    s.sampler.start()
    expect(s.lines).toHaveLength(1)
    s.sampler.stop()
    expect(s.cleared).toHaveBeenCalledWith('h')
    s.sampler.stop() // idempotente
    expect(s.cleared).toHaveBeenCalledTimes(1)
  })
})

describe('metricsFileFromEnv', () => {
  it('sem a variável (ou vazia) o amostrador não existe: nada é criado nem gravado', () => {
    expect(metricsFileFromEnv({})).toBeNull()
    expect(metricsFileFromEnv({ RAGX_PANEL_METRICS: '   ' })).toBeNull()
    expect(metricsFileFromEnv({ RAGX_PANEL_METRICS: 'C:\\Temp\\m.jsonl' })).toBe('C:\\Temp\\m.jsonl')
  })
})

/**
 * Amostrador de consumo do painel (RAGX-0177): RAM, CPU e filhos criados, a cada 5 s, em JSONL.
 *
 * Opt-in e só no processo principal: sem `RAGX_PANEL_METRICS` NADA é criado nem gravado
 * (`createRuntimeSamplerFromEnv` devolve `null`). Não há canal IPC novo. Só mede: nenhum consumo é consertado aqui.
 */
import { diffSpawns, snapshot as spawnSnapshot, type SpawnTotals } from './spawn-counter'
import type { PanelState, ProcessSample, RuntimeSample } from './runtime-summary'

export const SAMPLE_INTERVAL_MS = 5000

/** Forma mínima de `app.getAppMetrics()` que o amostrador usa. */
export interface AppMetric {
  pid: number
  type: string
  cpu: { percentCPUUsage: number }
  memory: { workingSetSize: number; privateBytes?: number }
}

export interface SamplerDeps {
  getAppMetrics: () => AppMetric[]
  getState: () => PanelState
  /** Fotografia dos acumulados de filhos (`spawn-counter.snapshot`). */
  spawns?: () => SpawnTotals
  /** Duração da última reconstrução do snapshot, em ms. */
  getSnapshotMs?: () => number | null
  now?: () => number
  /** Grava UMA linha JSONL. */
  write: (line: string) => void
  setInterval?: (fn: () => void, ms: number) => unknown
  clearInterval?: (handle: unknown) => void
}

export interface RuntimeSampler {
  start: () => void
  stop: () => void
  /** Tira uma amostra agora (usado pelo intervalo e pelos testes). */
  sampleOnce: () => RuntimeSample
}

const KB_PER_MB = 1024

function toProcessSample(m: AppMetric): ProcessSample {
  return {
    pid: m.pid,
    type: m.type,
    cpu: Math.round(m.cpu.percentCPUUsage * 100) / 100,
    // `workingSetSize` e `privateBytes` vêm em KB no Electron
    workingSetMB: Math.round((m.memory.workingSetSize / KB_PER_MB) * 10) / 10,
    privateMB: Math.round(((m.memory.privateBytes ?? 0) / KB_PER_MB) * 10) / 10,
  }
}

export function createRuntimeSampler(deps: SamplerDeps): RuntimeSampler {
  const now = deps.now ?? (() => Date.now())
  const spawns = deps.spawns ?? spawnSnapshot
  const setIntervalFn = deps.setInterval ?? ((fn, ms) => setInterval(fn, ms))
  const clearIntervalFn = deps.clearInterval ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  const startedAt = now()
  let lastAt = startedAt
  let lastSpawns = spawns()
  let first = true
  let lastCostMs: number | undefined
  let handle: unknown = null

  const sampleOnce = (): RuntimeSample => {
    const t0 = now()
    const current = spawns()
    const sample: RuntimeSample = {
      t: Math.round((t0 - startedAt) / 100) / 10,
      state: deps.getState(),
      // `percentCPUUsage` é medido DESDE a chamada anterior: a primeira amostra não vale e é descartada no resumo
      ...(first ? { warmup: true } : {}),
      processes: deps.getAppMetrics().map(toProcessSample),
      spawns: diffSpawns(lastSpawns, current),
      snapshotMs: deps.getSnapshotMs ? deps.getSnapshotMs() : null,
      dt: Math.round((t0 - lastAt) / 100) / 10,
      // o custo da amostra ANTERIOR (coletar + gravar): a atual só o sabe depois de gravada
      ...(lastCostMs !== undefined ? { sampleCostMs: lastCostMs } : {}),
    }
    first = false
    lastAt = t0
    lastSpawns = current
    deps.write(JSON.stringify(sample))
    lastCostMs = Math.round((now() - t0) * 100) / 100
    return sample
  }

  return {
    sampleOnce,
    start: () => {
      if (handle !== null) return
      sampleOnce() // a amostra de aquecimento: zera o CPU
      handle = setIntervalFn(sampleOnce, SAMPLE_INTERVAL_MS)
    },
    stop: () => {
      if (handle === null) return
      clearIntervalFn(handle)
      handle = null
    },
  }
}

/** O amostrador só existe com `RAGX_PANEL_METRICS=<arquivo.jsonl>`; sem a variável, `null` e nada é gravado. */
export function metricsFileFromEnv(env: NodeJS.ProcessEnv): string | null {
  const file = env.RAGX_PANEL_METRICS?.trim()
  return file ? file : null
}

import type { OllamaBenchmark } from '../../src/types/ragx-bridge'
import { httpGetJson, httpPostJson } from '../system/http'

const DEFAULT_MODEL = 'nomic-embed-text'
const DEFAULT_BASE = 'http://localhost:11434'
const TOTAL_TEXTS = 64
const BATCH_SIZE = 32
const WARMUP_TIMEOUT_MS = 120_000
const BATCH_TIMEOUT_MS = 120_000
const PS_TIMEOUT_MS = 5_000

export interface BenchDeps {
  httpPostJson: (url: string, body: unknown, timeoutMs: number) => Promise<{ status: number; json: unknown | null } | null>
  httpGetJson: (url: string, timeoutMs: number) => Promise<unknown | null>
  now: () => number // ms
  model: string | null // primeiro modelo em uso pelos projetos, ou null
  /** Base da API do Ollama. Padrão `http://localhost:11434`. */
  baseUrl?: string
}

export function defaultBenchDeps(model: string | null): BenchDeps {
  return { httpPostJson, httpGetJson, now: () => Date.now(), model, baseUrl: DEFAULT_BASE }
}

function fail(model: string, error: string): OllamaBenchmark {
  return {
    ok: false,
    chunksPerSecond: null,
    processor: 'unknown',
    vramMB: null,
    model,
    measuredAt: new Date().toISOString(),
    error,
  }
}

function errorText(json: unknown): string | null {
  if (json && typeof json === 'object' && 'error' in json) {
    const e = (json as { error: unknown }).error
    if (e !== undefined && e !== null && e !== '') return typeof e === 'string' ? e : JSON.stringify(e)
  }
  return null
}

/** Devolve o texto de erro legível de uma resposta de /api/embed, ou null se deu certo. */
function embedError(
  res: { status: number; json: unknown | null } | null,
  model: string,
  host: string,
): string | null {
  if (res === null) return `O Ollama não respondeu em ${host}.`
  const err = errorText(res.json)
  if (res.status === 404 || (err !== null && /not found/i.test(err))) {
    return `O modelo ${model} não está baixado neste Ollama.`
  }
  if (err !== null) return `Falha ao gerar embeddings: ${err}`
  if (res.status !== 200) return `Falha ao gerar embeddings: HTTP ${res.status}`
  return null
}

function processorOf(json: unknown, model: string): { processor: 'gpu' | 'cpu' | 'unknown'; vramMB: number | null } {
  const unknown = { processor: 'unknown' as const, vramMB: null }
  if (!json || typeof json !== 'object') return unknown
  const models = (json as { models?: unknown }).models
  if (!Array.isArray(models)) return unknown
  const base = (n: string): string => (n.endsWith(':latest') ? n.slice(0, -7) : n)
  for (const m of models) {
    if (!m || typeof m !== 'object') continue
    const { name, model: mid, size_vram: vram } = m as { name?: unknown; model?: unknown; size_vram?: unknown }
    const label = typeof name === 'string' ? name : typeof mid === 'string' ? mid : null
    if (label === null || base(label) !== base(model)) continue
    if (typeof vram !== 'number' || !Number.isFinite(vram)) return unknown
    if (vram > 0) return { processor: 'gpu', vramMB: Math.round(vram / 1048576) }
    if (vram === 0) return { processor: 'cpu', vramMB: null }
    return unknown
  }
  return unknown
}

function sampleTexts(): string[] {
  return Array.from({ length: TOTAL_TEXTS }, (_, i) => `trecho ${i} ` + 'lorem ipsum dolor sit amet '.repeat(16))
}

/** Mede chunks/s de embedding contra o Ollama e diz se roda em GPU ou CPU. Nunca lança. */
export async function runOllamaBenchmark(d: BenchDeps): Promise<OllamaBenchmark> {
  const model = d.model ?? DEFAULT_MODEL
  const base = (d.baseUrl ?? DEFAULT_BASE).replace(/\/+$/, '')
  const host = base.replace(/^https?:\/\//, '')
  const url = `${base}/api/embed`
  try {
    const warm = await d.httpPostJson(url, { model, input: ['aquecimento'] }, WARMUP_TIMEOUT_MS)
    const warmErr = embedError(warm, model, host)
    if (warmErr !== null) return fail(model, warmErr)

    const texts = sampleTexts()
    const start = d.now()
    for (let i = 0; i < texts.length; i += BATCH_SIZE) {
      const res = await d.httpPostJson(url, { model, input: texts.slice(i, i + BATCH_SIZE) }, BATCH_TIMEOUT_MS)
      const err = embedError(res, model, host)
      if (err !== null) return fail(model, err)
    }
    const seconds = Math.max((d.now() - start) / 1000, 0.001)

    let ps: unknown = null
    try {
      ps = await d.httpGetJson(`${base}/api/ps`, PS_TIMEOUT_MS)
    } catch {
      ps = null
    }
    const { processor, vramMB } = processorOf(ps, model)
    return {
      ok: true,
      chunksPerSecond: Math.round((TOTAL_TEXTS / seconds) * 10) / 10,
      processor,
      vramMB,
      model,
      measuredAt: new Date().toISOString(),
      error: null,
    }
  } catch (e) {
    return fail(model, `Falha ao gerar embeddings: ${e instanceof Error ? e.message : String(e)}`)
  }
}

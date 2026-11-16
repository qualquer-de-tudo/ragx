import type { UsageBlock, UsageGroup, UsageMetrics, UsageProject, UsageReport } from './types'

/**
 * Consumo real (RAGX-0205): `ragx usage --json`, lido das sessões do Claude Code de todos os perfis.
 *
 * Ler os transcripts é caro na primeira vez (centenas de MB; a CLI guarda um cache por arquivo e depois leva ~2 s),
 * e o painel não pode abrir mais processos por minuto do que antes. Por isso o resultado fica guardado aqui: no
 * máximo uma execução a cada `USAGE_TTL_MS`, e o "Atualizar" pedido pela pessoa no máximo uma vez por minuto. Uma
 * falha (CLI antiga, sem o comando) também espera o mesmo prazo antes de tentar de novo.
 */
export const USAGE_DAYS = 14
export const USAGE_TTL_MS = 10 * 60_000
export const USAGE_FORCE_MIN_MS = 60_000
/** A primeira leitura, sem cache, passa de 30 s numa máquina com muitas sessões. */
export const USAGE_TIMEOUT_MS = 180_000

export const USAGE_ARGS: readonly string[] = ['usage', '--days', String(USAGE_DAYS), '--json']

const METRICS: ReadonlyArray<[keyof UsageMetrics, string]> = [
  ['turns', 'turns'],
  ['prompts', 'prompts'],
  ['inputTokens', 'input_tokens'],
  ['cacheReadTokens', 'cache_read_tokens'],
  ['cacheCreationTokens', 'cache_creation_tokens'],
  ['outputTokens', 'output_tokens'],
  ['totalTokens', 'total_tokens'],
  ['searchCalls', 'search_calls'],
  ['readCalls', 'read_calls'],
  ['ragxCalls', 'ragx_calls'],
  ['otherCalls', 'other_calls'],
  ['imageReads', 'image_reads'],
  ['searchResultChars', 'search_result_chars'],
  ['readResultChars', 'read_result_chars'],
  ['ragxResultChars', 'ragx_result_chars'],
]

type Raw = Record<string, unknown>

function obj(v: unknown): Raw | null {
  return typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as Raw) : null
}

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : 0
}

function text(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null
}

function metrics(v: unknown): UsageMetrics {
  const r = obj(v) ?? {}
  const out = {} as UsageMetrics
  for (const [key, raw] of METRICS) out[key] = num(r[raw])
  return out
}

function group(v: unknown): UsageGroup {
  const r = obj(v) ?? {}
  const sessions = num(r.sessions)
  return { sessions, median: sessions > 0 ? metrics(r.median) : null, total: metrics(r.total) }
}

function block(r: Raw): UsageBlock {
  const a = obj(r.adoption) ?? {}
  return {
    sessions: num(r.sessions),
    firstAt: text(r.first_at),
    lastAt: text(r.last_at),
    all: group(r.all),
    withRagx: group(r.with_ragx),
    withoutRagx: group(r.without_ragx),
    adoption: {
      sessions: num(a.sessions),
      withRagx: num(a.with_ragx),
      hinted: num(a.hinted),
      reminded: num(a.reminded),
      ragxAfterReminder: num(a.ragx_after_reminder),
    },
  }
}

/**
 * Confere a saída da CLI campo a campo. Fica de fora o que o renderer não usa: o caminho de cada projeto (ele casa
 * pelo id) e os nomes dos perfis. `null` quando não é um relatório do `ragx usage`.
 */
export function parseUsage(raw: unknown): UsageReport | null {
  const r = obj(raw)
  if (r === null || r.source !== 'claude-code' || !Array.isArray(r.projects) || obj(r.overall) === null) return null
  const projects = r.projects.flatMap((item): UsageProject[] => {
    const p = obj(item)
    if (p === null) return []
    const name = text(p.name)
    if (name === null) return []
    return [{ id: text(p.id), name, ...block(p) }]
  })
  return {
    days: num(r.days),
    since: text(r.since),
    generatedAt: text(r.generated_at),
    charsPerToken: num(r.chars_per_token) || 4,
    sessionsScanned: num(r.sessions_scanned),
    sessionsOutsideProjects: num(r.sessions_outside_projects),
    overall: block(obj(r.overall) as Raw),
    projects,
  }
}

/** Uma execução por vez, guardada por `ttlMs`; `get(true)` ignora o prazo, mas não mais de uma vez por `forceMinMs`. */
export function createUsageCache(
  run: () => Promise<unknown>,
  opts: { now?: () => number; ttlMs?: number; forceMinMs?: number } = {},
): { get: (force?: boolean) => Promise<UsageReport> } {
  const now = opts.now ?? Date.now
  const ttl = opts.ttlMs ?? USAGE_TTL_MS
  const forceMin = opts.forceMinMs ?? USAGE_FORCE_MIN_MS
  let last: { at: number; report: UsageReport } | null = null
  let failure: { at: number; error: Error } | null = null
  let inFlight: Promise<UsageReport> | null = null

  function start(): Promise<UsageReport> {
    const p = Promise.resolve()
      .then(run)
      .then((raw) => {
        const report = parseUsage(raw)
        if (report === null) throw new Error('resposta inesperada de "ragx usage"')
        last = { at: now(), report }
        failure = null
        return report
      })
      .catch((err: unknown) => {
        failure = { at: now(), error: err instanceof Error ? err : new Error(String(err)) }
        throw failure.error
      })
      .finally(() => {
        if (inFlight === p) inFlight = null
      })
    inFlight = p
    return p
  }

  return {
    get(force = false): Promise<UsageReport> {
      if (inFlight) return inFlight
      const t = now()
      const recent = (at: number) => t - at < (force ? forceMin : ttl)
      if (last && recent(last.at)) return Promise.resolve(last.report)
      // Falhou há pouco: não tenta de novo ainda. Um resultado antigo vale mais do que um erro.
      if (failure && recent(failure.at)) return last ? Promise.resolve(last.report) : Promise.reject(failure.error)
      return start()
    },
  }
}

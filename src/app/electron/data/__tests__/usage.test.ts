import { describe, expect, it, vi } from 'vitest'
import { createUsageCache, parseUsage, USAGE_FORCE_MIN_MS, USAGE_TTL_MS } from '../usage'

function grupo(sessions: number, median: Record<string, number> | null) {
  return { sessions, median: median ?? { turns: null, total_tokens: null }, total: { turns: sessions * 10 } }
}

/** Saída de `ragx usage --json`, como a CLI imprime (snake_case). */
function raw(over: Record<string, unknown> = {}) {
  const bloco = {
    sessions: 3,
    first_at: '2026-11-03T12:00:00Z',
    last_at: '2026-11-16T15:00:00Z',
    all: grupo(3, { turns: 6, total_tokens: 900_000, cache_read_tokens: 800_000 }),
    with_ragx: grupo(1, { turns: 3, total_tokens: 400_000, ragx_calls: 2 }),
    without_ragx: grupo(2, { turns: 8, total_tokens: 1_200_000, search_calls: 12, search_result_chars: 8000 }),
    adoption: { sessions: 3, with_ragx: 1, hinted: 2, reminded: 2, ragx_after_reminder: 1 },
    profiles: { padrão: 2, empresa: 1 },
  }
  return {
    source: 'claude-code',
    kind: 'observation',
    note: 'Observação, não experimento',
    days: 14,
    since: '2026-11-02T00:00:00Z',
    generated_at: '2026-11-16T15:51:44Z',
    chars_per_token: 4,
    profiles: [{ name: 'padrão', sessions: 2 }],
    sessions_scanned: 10,
    sessions_outside_projects: 7,
    overall: bloco,
    projects: [{ id: 'p1', name: 'Juriflux', path: 'C:/projects/Juriflux', ...bloco }],
    ...over,
  }
}

describe('parseUsage', () => {
  it('converte para camelCase e deixa de fora o caminho do projeto e os perfis', () => {
    const r = parseUsage(raw())
    expect(r).not.toBeNull()
    expect(r?.sessionsOutsideProjects).toBe(7)
    expect(r?.projects[0].id).toBe('p1')
    expect(r?.projects[0].withoutRagx.median?.searchCalls).toBe(12)
    expect(r?.projects[0].withoutRagx.median?.searchResultChars).toBe(8000)
    expect(r?.projects[0].adoption).toEqual({ sessions: 3, withRagx: 1, hinted: 2, reminded: 2, ragxAfterReminder: 1 })
    expect(JSON.stringify(r)).not.toContain('C:/projects')
    expect(JSON.stringify(r)).not.toContain('empresa')
  })

  it('grupo sem sessão não tem mediana; número inválido vira 0', () => {
    const r = parseUsage(raw({ overall: { sessions: 'x', with_ragx: grupo(0, null), all: grupo(1, { turns: -3, total_tokens: Number.NaN }) } }))
    expect(r?.overall.withRagx.median).toBeNull()
    expect(r?.overall.sessions).toBe(0)
    expect(r?.overall.all.median?.turns).toBe(0)
    expect(r?.overall.all.median?.totalTokens).toBe(0)
  })

  it('o que não é relatório do ragx usage vira null; projeto sem nome fica de fora', () => {
    expect(parseUsage(null)).toBeNull()
    expect(parseUsage({ ...raw(), source: 'outro' })).toBeNull()
    expect(parseUsage({ ...raw(), projects: 'x' })).toBeNull()
    expect(parseUsage(raw({ projects: [{ id: 'x' }, 7] }))?.projects).toEqual([])
  })
})

describe('createUsageCache: no máximo um processo a cada 10 minutos', () => {
  function relogio() {
    let t = 1_000_000
    return { now: () => t, passar: (ms: number) => (t += ms) }
  }

  it('guarda o resultado pelo prazo e junta pedidos simultâneos numa execução só', async () => {
    const c = relogio()
    const run = vi.fn(async () => raw())
    const cache = createUsageCache(run, { now: c.now })
    const [a, b] = await Promise.all([cache.get(), cache.get()])
    expect(a).toBe(b)
    c.passar(USAGE_TTL_MS - 1)
    await cache.get()
    expect(run).toHaveBeenCalledTimes(1)
    c.passar(1)
    await cache.get()
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('"Atualizar" ignora o prazo, mas não mais de uma vez por minuto', async () => {
    const c = relogio()
    const run = vi.fn(async () => raw())
    const cache = createUsageCache(run, { now: c.now })
    await cache.get()
    await cache.get(true)
    expect(run).toHaveBeenCalledTimes(1)
    c.passar(USAGE_FORCE_MIN_MS)
    await cache.get(true)
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('falha (CLI antiga, sem o comando) também espera o prazo antes de tentar de novo', async () => {
    const c = relogio()
    const run = vi.fn(async () => {
      throw new Error("No such command 'usage'")
    })
    const cache = createUsageCache(run, { now: c.now })
    await expect(cache.get()).rejects.toThrow(/usage/)
    await expect(cache.get()).rejects.toThrow(/usage/)
    expect(run).toHaveBeenCalledTimes(1)
    c.passar(USAGE_TTL_MS)
    await expect(cache.get()).rejects.toThrow()
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('saída que não é relatório é falha; um resultado antigo vale mais do que o erro', async () => {
    const c = relogio()
    const run = vi.fn<() => Promise<unknown>>().mockResolvedValueOnce(raw()).mockResolvedValueOnce({ ok: true })
    const cache = createUsageCache(run, { now: c.now })
    const primeiro = await cache.get()
    c.passar(USAGE_FORCE_MIN_MS)
    await expect(cache.get(true)).rejects.toThrow('resposta inesperada de "ragx usage"')
    expect(await cache.get()).toBe(primeiro)
    expect(run).toHaveBeenCalledTimes(2)
  })
})

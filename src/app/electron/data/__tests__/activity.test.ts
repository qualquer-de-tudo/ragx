import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { ActivityTail, INITIAL_TAIL_BYTES, type TailFs } from '../activity'

const NOW = Date.parse('2026-09-29T20:00:00Z')
const SOURCE = { id: 'p1', name: 'Juriflux', path: 'C:/proj/juriflux' }
const MCP = path.join(SOURCE.path, '.ragx', 'logs', 'mcp.jsonl')
const CLI = path.join(SOURCE.path, '.ragx', 'logs', 'cli.jsonl')

function fakeFs() {
  const files = new Map<string, Buffer>()
  const fs: TailFs = {
    size: (f) => files.get(f)?.length ?? null,
    read: (f, start, end) => (files.get(f) as Buffer).subarray(start, end).toString('utf8'),
  }
  return {
    fs,
    set: (f: string, text: string) => files.set(f, Buffer.from(text, 'utf8')),
    append: (f: string, text: string) => files.set(f, Buffer.concat([files.get(f) ?? Buffer.alloc(0), Buffer.from(text, 'utf8')])),
  }
}

const mcp = (ts: string, tool = 'build_context', extra: Record<string, unknown> = {}) =>
  JSON.stringify({ ts, tool, ms: 12.5, project: 'Juriflux', ...extra }) + '\n'

function tail(f: ReturnType<typeof fakeFs>) {
  return new ActivityTail({ fs: f.fs, now: () => NOW })
}

describe('ActivityTail', () => {
  it('lê o que já existe e depois só o que foi acrescentado', () => {
    const f = fakeFs()
    f.set(MCP, mcp('2026-09-29T19:00:00Z') + mcp('2026-09-29T19:30:00Z', 'search_hybrid'))
    const t = tail(f)
    expect(t.poll([SOURCE]).map((e) => e.name)).toEqual(['build_context', 'search_hybrid'])
    expect(t.poll([SOURCE])).toEqual([])

    f.append(MCP, mcp('2026-09-29T19:59:00Z', 'get_chunk', { client: 'claude-code', profile: 'empresa', session: 'abcd1234', tokens_delivered: 900, baseline_tokens: 9000 }))
    const [novo] = t.poll([SOURCE])
    expect(novo).toMatchObject({
      name: 'get_chunk', kind: 'mcp', projectId: 'p1', projectName: 'Juriflux',
      profile: 'empresa', client: 'claude-code', session: 'abcd1234', tokensDelivered: 900, baselineTokens: 9000,
    })
    expect(t.recent()).toHaveLength(3)
  })

  it('linha no meio de uma escrita espera terminar', () => {
    const f = fakeFs()
    f.set(MCP, mcp('2026-09-29T19:00:00Z'))
    const t = tail(f)
    t.poll([SOURCE])
    const linha = mcp('2026-09-29T19:10:00Z', 'search_hybrid')
    f.append(MCP, linha.slice(0, 20))
    expect(t.poll([SOURCE])).toEqual([])
    f.append(MCP, linha.slice(20))
    expect(t.poll([SOURCE]).map((e) => e.name)).toEqual(['search_hybrid'])
  })

  it('arquivo truncado ou recriado recomeça do início', () => {
    const f = fakeFs()
    f.set(MCP, mcp('2026-09-29T19:00:00Z') + mcp('2026-09-29T19:01:00Z'))
    const t = tail(f)
    t.poll([SOURCE])
    f.set(MCP, mcp('2026-09-29T19:50:00Z', 'refresh'))
    expect(t.poll([SOURCE]).map((e) => e.name)).toEqual(['refresh'])
  })

  it('linha inválida e evento com mais de 24 h ficam de fora, sem derrubar o resto', () => {
    const f = fakeFs()
    f.set(MCP, 'não é json\n' + '{"ts": 42}\n' + mcp('2026-09-27T10:00:00Z') + mcp('2026-09-29T19:00:00Z', 'get_dictionary'))
    expect(tail(f).poll([SOURCE]).map((e) => e.name)).toEqual(['get_dictionary'])
  })

  it('comandos da CLI e início de sessão viram eventos próprios, do mais antigo ao mais novo', () => {
    const f = fakeFs()
    f.set(CLI, JSON.stringify({ ts: '2026-09-29T19:20:00Z', command: 'session_start', project: 'Juriflux', profile: 'padrão' }) + '\n'
      + JSON.stringify({ ts: '2026-09-29T19:40:00Z', command: 'search', ms: 800, ok: false, project: 'Juriflux' }) + '\n')
    f.set(MCP, mcp('2026-09-29T19:30:00Z'))
    const eventos = tail(f).poll([SOURCE])
    expect(eventos.map((e) => [e.kind, e.name])).toEqual([['session', 'session_start'], ['mcp', 'build_context'], ['cli', 'search']])
    expect(eventos[2].ok).toBe(false)
  })

  it('log grande: a primeira leitura pega só o fim, sem a linha cortada', () => {
    const f = fakeFs()
    const velha = mcp('2026-09-29T18:00:00Z', 'velha')
    let texto = ''
    while (Buffer.byteLength(texto) < INITIAL_TAIL_BYTES + 5000) texto += velha
    f.set(MCP, texto + mcp('2026-09-29T19:59:00Z', 'nova'))
    const eventos = tail(f).poll([SOURCE])
    expect(eventos.at(-1)?.name).toBe('nova')
    expect(eventos.every((e) => e.name === 'velha' || e.name === 'nova')).toBe(true)
    expect(eventos.length).toBeLessThan(texto.length / velha.length)
  })

  it('acento no meio do arquivo não desalinha o deslocamento (bytes, não caracteres)', () => {
    const f = fakeFs()
    f.set(MCP, mcp('2026-09-29T19:00:00Z', 'build_context', { profile: 'padrão', note: 'ção' }))
    const t = tail(f)
    t.poll([SOURCE])
    f.append(MCP, mcp('2026-09-29T19:05:00Z', 'search_hybrid', { profile: 'padrão' }))
    const [ev] = t.poll([SOURCE])
    expect(ev).toMatchObject({ name: 'search_hybrid', profile: 'padrão' })
    expect(t.poll([SOURCE])).toEqual([])
  })

  it('projeto sem pasta local ou sem log é ignorado', () => {
    const f = fakeFs()
    expect(tail(f).poll([{ id: 'fed', name: 'Fed', path: null }, SOURCE])).toEqual([])
  })
})

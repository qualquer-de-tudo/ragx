import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { ActivityTail, INITIAL_TAIL_BYTES, type TailFs } from '../activity'
import { ADOPTION_DAYS, computeAdoption, type AdoptionSession } from '../adoption'

const NOW = Date.parse('2026-10-01T12:00:00Z')
const day = (d: number, h = 0) => new Date(NOW - d * 86_400_000 - h * 3_600_000).toISOString()

function s(over: Partial<AdoptionSession> = {}): AdoptionSession {
  return {
    projectId: 'p1', projectName: 'P1', session: 'aaaa1111', startedAt: day(1), firstAt: day(1), lastAt: day(1), calls: 0, events: 1, ...over,
  }
}

describe('computeAdoption', () => {
  it('3 session_start e 1 sessão com chamada MCP resultam em 1 de 3', () => {
    const r = computeAdoption([s({ session: 'a', calls: 2 }), s({ session: 'b' }), s({ session: 'c' })], NOW)
    expect(r).toMatchObject({ sessions: 3, withCalls: 1, withoutCalls: 2, unidentified: 0, callsWithoutStart: 0 })
    expect(r.byProject).toEqual([{ projectId: 'p1', projectName: 'P1', sessions: 3, withCalls: 1 }])
  })

  it('o mesmo id de sessão em projetos diferentes não funde', () => {
    const r = computeAdoption([s({ session: 'x', calls: 1 }), s({ session: 'x', projectId: 'p2', projectName: 'P2' })], NOW)
    expect(r.sessions).toBe(2)
    expect(r.byProject.map((p) => [p.projectId, p.withCalls])).toEqual([['p1', 1], ['p2', 0]])
  })

  it('sem session vai para unidentified e fica fora da razão', () => {
    const r = computeAdoption([s({ session: null, startedAt: null, events: 4, calls: 4 }), s({ session: 'a' })], NOW)
    expect(r.unidentified).toBe(4)
    expect(r.sessions).toBe(1)
  })

  it('chamada de sessão sem session_start conta em callsWithoutStart e fica fora', () => {
    const r = computeAdoption([s({ session: 'a', startedAt: null, calls: 3 }), s({ session: 'b', startedAt: null, calls: 0 })], NOW)
    expect(r.callsWithoutStart).toBe(1)
    expect(r.sessions).toBe(0)
  })

  it('janela de 14 dias: sessão mais velha sai; since é o evento mais antigo realmente lido', () => {
    const r = computeAdoption([s({ session: 'velha', firstAt: day(20), lastAt: day(16) }), s({ session: 'a', firstAt: day(9), lastAt: day(2) }), s({ session: 'b', firstAt: day(3) })], NOW)
    expect(ADOPTION_DAYS).toBe(14)
    expect(r.sessions).toBe(2)
    expect(r.since).toBe(day(9))
  })

  it('lista vazia: zeros, since nulo, sem exceção', () => {
    expect(computeAdoption([], NOW)).toEqual({ since: null, sessions: 0, withCalls: 0, withoutCalls: 0, unidentified: 0, callsWithoutStart: 0, byProject: [] })
  })

  it('o resumo só tem contagens, datas e ids de projeto (nenhuma consulta ou argumento)', () => {
    const r = computeAdoption([s({ calls: 1 })], NOW)
    expect(Object.keys(r).sort()).toEqual(['byProject', 'callsWithoutStart', 'sessions', 'since', 'unidentified', 'withCalls', 'withoutCalls'])
    expect(Object.keys(r.byProject[0]).sort()).toEqual(['projectId', 'projectName', 'sessions', 'withCalls'])
  })
})

// --- o índice por sessão do ActivityTail ---
const SOURCE = { id: 'p1', name: 'P1', path: 'C:/proj/p1' }
const MCP = path.join(SOURCE.path, '.ragx', 'logs', 'mcp.jsonl')
const CLI = path.join(SOURCE.path, '.ragx', 'logs', 'cli.jsonl')

function fakeFs() {
  const files = new Map<string, Buffer>()
  const reads: Array<[number, number]> = []
  const fs: TailFs = {
    size: (f) => files.get(f)?.length ?? null,
    read: (f, a, b) => {
      reads.push([a, b])
      return (files.get(f) as Buffer).subarray(a, b).toString('utf8')
    },
  }
  return { fs, reads, set: (f: string, t: string) => files.set(f, Buffer.from(t, 'utf8')) }
}
const cli = (ts: string, session: string | null) => JSON.stringify({ ts, command: 'session_start', project: 'P1', ...(session ? { session } : {}) }) + '\n'
const mcp = (ts: string, session: string | null) => JSON.stringify({ ts, tool: 'build_context', ms: 1, project: 'P1', ...(session ? { session } : {}) }) + '\n'

describe('ActivityTail: índice por sessão (RAGX-0190)', () => {
  it('sobrevive ao corte de 24 h do feed (14 dias de adoção contra 24 h do feed)', () => {
    const f = fakeFs()
    f.set(CLI, cli(day(5), 'velha001') + cli(day(0, 1), 'nova0001'))
    f.set(MCP, mcp(day(5, -1), 'velha001'))
    const t = new ActivityTail({ fs: f.fs, now: () => NOW })
    t.poll([SOURCE])
    expect(t.recent().map((e) => e.session)).toEqual(['nova0001']) // o feed só tem as últimas 24 h
    const r = computeAdoption(t.sessions(), NOW)
    expect(r.sessions).toBe(2)
    expect(r.withCalls).toBe(1) // a sessão de 5 dias atrás chamou o RAGX
  })

  it('linha corrompida e sem session não lançam e caem nos contadores certos; log ausente dá zero', () => {
    const f = fakeFs()
    f.set(CLI, 'isso nao e json\n' + cli(day(1), null))
    f.set(MCP, mcp(day(1), null))
    const t = new ActivityTail({ fs: f.fs, now: () => NOW })
    t.poll([SOURCE])
    const r = computeAdoption(t.sessions(), NOW)
    expect(r.unidentified).toBe(2)
    expect(r.sessions).toBe(0)
    expect(computeAdoption(new ActivityTail({ fs: fakeFs().fs, now: () => NOW }).sessions(), NOW).sessions).toBe(0)
  })

  it('a leitura continua por deslocamento: a segunda volta não relê o arquivo', () => {
    const f = fakeFs()
    f.set(CLI, cli(day(1), 'a'))
    const t = new ActivityTail({ fs: f.fs, now: () => NOW })
    t.poll([SOURCE])
    const antes = f.reads.length
    t.poll([SOURCE])
    t.sessions()
    expect(f.reads.length).toBe(antes)
  })

  it('primeira leitura parcial: só o fim do arquivo entra e `since` diz até onde se leu', () => {
    const f = fakeFs()
    const linhas = Array.from({ length: 8000 }, (_, i) => cli(new Date(NOW - (8000 - i) * 60_000).toISOString(), `s${i}`)).join('')
    expect(linhas.length).toBeGreaterThan(INITIAL_TAIL_BYTES)
    f.set(CLI, linhas)
    const t = new ActivityTail({ fs: f.fs, now: () => NOW })
    t.poll([SOURCE])
    const r = computeAdoption(t.sessions(), NOW)
    expect(r.sessions).toBeLessThan(8000)
    expect(Date.parse(r.since as string)).toBeGreaterThan(NOW - 8000 * 60_000)
  })
})

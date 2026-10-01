import { describe, expect, it } from 'vitest'
import { groupSessions } from '../sessions'
import type { ActivityEvent } from '../types/ragx-bridge'

let n = 0
function ev(over: Partial<ActivityEvent> = {}): ActivityEvent {
  n += 1
  return {
    id: `e${n}`, ts: '2026-10-01T10:00:00Z', projectId: 'p1', projectName: 'P1', kind: 'mcp', name: 'build_context', ms: 10,
    ok: null, tokensDelivered: null, baselineTokens: null, errCode: null, respChars: null, respTokens: null,
    client: 'claude-code', profile: 'empresa', session: 'aaaa1111', ...over,
  }
}
const at = (min: number) => `2026-10-01T10:${String(min).padStart(2, '0')}:00Z`

describe('groupSessions', () => {
  const fixture = [
    // sessão "aaaa1111" com session_start repetido (subagentes)
    ev({ ts: at(0), kind: 'session', name: 'session_start', session: 'aaaa1111' }),
    ev({ ts: at(1), kind: 'session', name: 'session_start', session: 'aaaa1111' }),
    ev({ ts: at(2), kind: 'session', name: 'session_start', session: 'aaaa1111' }),
    ev({ ts: at(3), kind: 'mcp', name: 'search_hybrid', session: 'aaaa1111', ok: true, tokensDelivered: 100, baselineTokens: 1000 }),
    ev({ ts: at(4), kind: 'mcp', name: 'build_context', session: 'aaaa1111', ok: false, errCode: 'not_found' }),
    ev({ ts: at(5), kind: 'cli', name: 'search', session: 'aaaa1111' }),
    ev({ ts: at(10), kind: 'session', name: 'session_start', session: 'bbbb2222' }), // abriu e não usou
    ev({ ts: at(20), kind: 'mcp', name: 'get_chunk', session: 'cccc3333' }),
    // o MESMO id em outro projeto: não funde
    ev({ ts: at(21), kind: 'mcp', name: 'get_chunk', session: 'cccc3333', projectId: 'p2', projectName: 'P2' }),
    // sem sessão: um grupo por projeto
    ev({ ts: at(30), session: null }),
    ev({ ts: at(31), session: null }),
    ev({ ts: at(32), session: null, projectId: 'p2', projectName: 'P2' }),
  ]

  it('3 sessões, o mesmo id em outro projeto e 1 grupo sem sessão por projeto, sem fundir projetos', () => {
    const g = groupSessions(fixture, Date.now())
    expect(g).toHaveLength(6)
    expect(g.filter((x) => x.session === 'cccc3333').map((x) => x.projectId).sort()).toEqual(['p1', 'p2'])
    expect(g.filter((x) => x.session === null).map((x) => x.projectId).sort()).toEqual(['p1', 'p2'])
  })

  it('os inícios repetidos contam em starts, não como várias sessões', () => {
    const a = groupSessions(fixture).find((x) => x.session === 'aaaa1111')!
    expect(a.starts).toBe(3)
    expect(a.mcpCalls).toBe(2)
    expect(a.cliCalls).toBe(1)
    expect(a.usedRagx).toBe(true)
  })

  it('sessão que só abriu (session_start) não usou o RAGX', () => {
    const b = groupSessions(fixture).find((x) => x.session === 'bbbb2222')!
    expect(b.usedRagx).toBe(false)
    expect(b.mcpCalls + b.cliCalls).toBe(0)
  })

  it('failures: contagem quando há ok, null ("sem dado") quando nenhum evento o traz', () => {
    const all = groupSessions(fixture)
    expect(all.find((x) => x.session === 'aaaa1111')!.failures).toBe(1)
    expect(all.find((x) => x.session === 'cccc3333' && x.projectId === 'p1')!.failures).toBeNull()
  })

  it('soma só tokens com as duas medidas, agrupa por ferramenta e ordena os eventos no tempo', () => {
    const a = groupSessions([...fixture].reverse()).find((x) => x.session === 'aaaa1111')!
    expect(a.delivered).toBe(100)
    expect(a.baseline).toBe(1000)
    expect(a.byTool.map((t) => t.name).sort()).toEqual(['build_context', 'search', 'search_hybrid'])
    expect(a.events.map((e) => e.ts)).toEqual([...a.events.map((e) => e.ts)].sort())
    expect(a.startedAt).toBe(at(0))
    expect(a.lastAt).toBe(at(5))
  })

  it('ordena do grupo mais recente ao mais antigo e aceita lista vazia', () => {
    const lastAts = groupSessions(fixture).map((g) => Date.parse(g.lastAt))
    expect(lastAts).toEqual([...lastAts].sort((a, b) => b - a))
    expect(groupSessions([])).toEqual([])
  })

  it('500 eventos agrupam depressa', () => {
    const many = Array.from({ length: 500 }, (_, i) => ev({ ts: at(i % 60), session: `s${i % 25}`, projectId: `p${i % 4}` }))
    const t0 = performance.now()
    const g = groupSessions(many)
    const took = performance.now() - t0
    console.log(`[0188] groupSessions(500 eventos) em ${took.toFixed(2)} ms, ${g.length} grupos`)
    expect(took).toBeLessThan(200)
  })
})

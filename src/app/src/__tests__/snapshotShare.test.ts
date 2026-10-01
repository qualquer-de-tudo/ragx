import { describe, expect, it } from 'vitest'
import { sameData, shareById, shareSnapshot } from '../snapshotShare'
import type { Snapshot } from '../types/ragx-bridge'
import { snap } from '../test/snap'

const base = (over: Partial<Snapshot> = {}): Snapshot => ({
  projects: [snap({ id: 'a' }), snap({ id: 'b' }), snap({ id: 'c' })],
  generatedAt: '2026-10-01T12:00:00Z',
  connectionsHealth: 'ok',
  ...over,
})

describe('shareSnapshot', () => {
  it('mesmo conteúdo com generatedAt diferente devolve o anterior', () => {
    const prev = base()
    const next = structuredClone({ ...prev, generatedAt: '2026-10-01T12:00:05Z' })
    expect(shareSnapshot(prev, next)).toBe(prev)
  })

  it('sem anterior devolve o novo', () => {
    const next = base()
    expect(shareSnapshot(null, next)).toBe(next)
  })

  it('um projeto alterado troca só a referência dele', () => {
    const prev = base()
    const next = structuredClone(prev)
    next.projects[1].telemetry.totalCalls = 7
    const out = shareSnapshot(prev, next)
    expect(out).not.toBe(prev)
    expect(out.projects[0]).toBe(prev.projects[0])
    expect(out.projects[1]).not.toBe(prev.projects[1])
    expect(out.projects[1].telemetry.totalCalls).toBe(7)
    expect(out.projects[2]).toBe(prev.projects[2])
  })

  it('projeto novo e projeto removido; a ordem de next é a que vale', () => {
    const prev = base()
    const novo = snap({ id: 'd' })
    const next = structuredClone({ ...prev, projects: [prev.projects[2], prev.projects[0], novo] })
    const out = shareSnapshot(prev, next)
    expect(out.projects.map((p) => p.id)).toEqual(['c', 'a', 'd'])
    expect(out.projects[0]).toBe(prev.projects[2])
    expect(out.projects[1]).toBe(prev.projects[0])
    expect(out.projects[2]).toEqual(novo)
  })

  it('mudança fora dos projetos (connectionsHealth) gera objeto novo e mantém os projetos', () => {
    const prev = base()
    const out = shareSnapshot(prev, structuredClone({ ...prev, connectionsHealth: 'error' as const }))
    expect(out).not.toBe(prev)
    expect(out.connectionsHealth).toBe('error')
    expect(out.projects).toBe(prev.projects)
  })
})

describe('shareById e sameData', () => {
  it('lista igual devolve a mesma lista; item novo mantém os antigos', () => {
    const prev = [{ id: 'x', n: 1 }, { id: 'y', n: 2 }]
    expect(shareById(prev, structuredClone(prev))).toBe(prev)
    const out = shareById(prev, [...structuredClone(prev), { id: 'z', n: 3 }])
    expect(out[0]).toBe(prev[0])
    expect(out[1]).toBe(prev[1])
    expect(out).toHaveLength(3)
  })

  it('compara estruturalmente, inclusive null e listas', () => {
    expect(sameData({ a: [1, { b: null }] }, { a: [1, { b: null }] })).toBe(true)
    expect(sameData({ a: [1] }, { a: [1, 2] })).toBe(false)
    expect(sameData({ a: null }, { a: undefined })).toBe(false)
    expect(sameData([], {})).toBe(false)
  })
})

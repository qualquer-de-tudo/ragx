import { afterEach, describe, expect, it, vi } from 'vitest'
import { CACHE_KEY, WRITE_EVERY_MS, readCachedSnapshot, resetCacheThrottle, writeCachedSnapshot } from '../snapshotCache'
import { snap } from '../test/snap'
import type { Snapshot } from '../types/ragx-bridge'

const live: Snapshot = { projects: [snap({ id: 'a' }), snap({ id: 'b' })], generatedAt: '2026-10-01T12:00:00Z', connectionsHealth: 'ok' }

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
  resetCacheThrottle()
})

describe('snapshotCache', () => {
  it('ida e volta, sem connectionsHealth', () => {
    writeCachedSnapshot(live, 1_000_000)
    const back = readCachedSnapshot()
    expect(back).not.toBeNull()
    expect(back!.projects.map((p) => p.id)).toEqual(['a', 'b'])
    expect(back!.generatedAt).toBe(live.generatedAt)
    expect(back).not.toHaveProperty('connectionsHealth')
    expect(window.localStorage.getItem(CACHE_KEY)).not.toContain('connectionsHealth')
  })

  it('no máximo uma gravação a cada 15 s', () => {
    writeCachedSnapshot(live, 1_000_000)
    writeCachedSnapshot({ ...live, generatedAt: '2026-10-01T12:00:05Z' }, 1_000_000 + WRITE_EVERY_MS - 1)
    expect(readCachedSnapshot()!.generatedAt).toBe('2026-10-01T12:00:00Z')
    writeCachedSnapshot({ ...live, generatedAt: '2026-10-01T12:00:20Z' }, 1_000_000 + WRITE_EVERY_MS)
    expect(readCachedSnapshot()!.generatedAt).toBe('2026-10-01T12:00:20Z')
  })

  it('hub vazio não é guardado', () => {
    writeCachedSnapshot({ projects: [], generatedAt: live.generatedAt }, 1_000_000)
    expect(readCachedSnapshot()).toBeNull()
  })

  it.each([
    ['JSON quebrado', '{nao e json'],
    ['esquema de outra versão', JSON.stringify({ v: 2, snapshot: { projects: [], generatedAt: live.generatedAt } })],
    ['sem projects', JSON.stringify({ v: 1, snapshot: { generatedAt: live.generatedAt } })],
    ['projeto sem telemetria', JSON.stringify({ v: 1, snapshot: { generatedAt: live.generatedAt, projects: [{ id: 'x', name: 'x', exists: true }] } })],
    ['data inválida', JSON.stringify({ v: 1, snapshot: { generatedAt: 'ontem', projects: [] } })],
    ['não é objeto', '42'],
  ])('%s vira null, sem exceção', (_name, raw) => {
    window.localStorage.setItem(CACHE_KEY, raw)
    expect(readCachedSnapshot()).toBeNull()
  })

  it('localStorage lançando: leitura devolve null e escrita não levanta', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('cheio')
    })
    expect(readCachedSnapshot()).toBeNull()
    expect(() => writeCachedSnapshot(live, 1_000_000)).not.toThrow()
  })
})

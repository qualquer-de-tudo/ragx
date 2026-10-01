import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useSnapshot } from '../useSnapshot'
import { writeCachedSnapshot } from '../../snapshotCache'
import { installBridge, snap } from '../../test/snap'
import type { Snapshot } from '../../types/ragx-bridge'

const cached: Snapshot = { projects: [snap({ id: 'velho', name: 'Velho' })], generatedAt: '2026-10-01T10:00:00Z' }
const fresh: Snapshot = { projects: [snap({ id: 'novo', name: 'Novo' })], generatedAt: '2026-10-01T12:00:00Z' }

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

describe('useSnapshot: cache, erro e retry (RAGX-0182)', () => {
  it('começa pelo cache e troca pelo vivo quando chega', async () => {
    writeCachedSnapshot(cached, 1_000_000)
    let answer: (s: Snapshot) => void = () => {}
    installBridge({ getSnapshot: vi.fn(() => new Promise<Snapshot>((r) => (answer = r))) })
    const { result } = renderHook(() => useSnapshot())
    expect(result.current.fromCache).toBe(true)
    expect(result.current.snapshot!.projects[0].id).toBe('velho')
    await act(async () => answer(fresh))
    expect(result.current.fromCache).toBe(false)
    expect(result.current.snapshot!.projects[0].id).toBe('novo')
  })

  it('sem cache e sem resposta ainda: snapshot null, sem erro', () => {
    installBridge({ getSnapshot: vi.fn(() => new Promise<Snapshot>(() => {})) })
    const { result } = renderHook(() => useSnapshot())
    expect(result.current).toMatchObject({ snapshot: null, fromCache: false, error: null })
  })

  it('getSnapshot rejeitando sem nada na tela vira error; retry chama de novo e, dando certo, segue', async () => {
    const getSnapshot = vi
      .fn()
      .mockRejectedValueOnce(new Error("Error invoking remote method 'ragx:getSnapshot': Error: hub corrompido"))
      .mockResolvedValueOnce(fresh)
    installBridge({ getSnapshot })
    const { result } = renderHook(() => useSnapshot())
    await waitFor(() => expect(result.current.error).toBe('hub corrompido'))
    expect(result.current.snapshot).toBeNull()
    act(() => result.current.retry())
    await waitFor(() => expect(result.current.snapshot?.projects[0].id).toBe('novo'))
    expect(result.current.error).toBeNull()
    expect(getSnapshot).toHaveBeenCalledTimes(2)
  })

  it('com cache na tela, a falha do vivo não vira erro', async () => {
    writeCachedSnapshot(cached, 1_000_000)
    installBridge({ getSnapshot: vi.fn().mockRejectedValue(new Error('x')) })
    const { result } = renderHook(() => useSnapshot())
    await act(async () => {})
    expect(result.current.error).toBeNull()
    expect(result.current.snapshot!.projects[0].id).toBe('velho')
    expect(result.current.fromCache).toBe(true)
  })

  it('um push mais novo que a resposta inicial continua valendo (ordem por generatedAt)', async () => {
    let answer: (s: Snapshot) => void = () => {}
    let push: (s: Snapshot) => void = () => {}
    installBridge({
      getSnapshot: vi.fn(() => new Promise<Snapshot>((r) => (answer = r))),
      onSnapshot: vi.fn((cb: (s: Snapshot) => void) => {
        push = cb
        return () => {}
      }),
    })
    const { result } = renderHook(() => useSnapshot())
    act(() => push(fresh))
    await act(async () => answer(cached)) // resposta inicial mais velha que o push
    expect(result.current.snapshot!.projects[0].id).toBe('novo')
  })
})

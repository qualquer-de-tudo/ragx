import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useSnapshot } from '../useSnapshot'
import type { Snapshot } from '../../types/ragx-bridge'

const emptySnapshot: Snapshot = { projects: [], generatedAt: '2026-09-21T10:00:00Z' }

describe('useSnapshot', () => {
  let listeners: Array<(s: Snapshot) => void> = []

  beforeEach(() => {
    listeners = []
    window.ragx = {
      getSnapshot: vi.fn().mockResolvedValue(emptySnapshot),
      onSnapshot: vi.fn((cb: (s: Snapshot) => void) => {
        listeners.push(cb)
        return () => {
          const i = listeners.indexOf(cb)
          if (i >= 0) listeners.splice(i, 1)
        }
      }),
      getProjectStatus: vi.fn(),
      runTrial: vi.fn(),
      getIndexRuns: vi.fn(),
      runSecurityScan: vi.fn(),
      getConnections: vi.fn(),
      onConnections: vi.fn(() => () => {}),
      listJobs: vi.fn(),
      onJobs: vi.fn(() => () => {}),
      enqueueJob: vi.fn(),
      cancelJob: vi.fn(),
      pickFolder: vi.fn(),
      discover: vi.fn(),
      getSettings: vi.fn(),
      setOnboardingDone: vi.fn(),
      runOllamaBenchmark: vi.fn(),
      getClaudeIntegration: vi.fn(),
      setClaudeIntegration: vi.fn(),
    }
  })

  it('carrega o snapshot inicial via getSnapshot', async () => {
    const { result } = renderHook(() => useSnapshot())
    await waitFor(() => expect(result.current.snapshot).toEqual(emptySnapshot))
    expect(window.ragx.getSnapshot).toHaveBeenCalledOnce()
  })

  it('assina onSnapshot e desinscreve ao desmontar', async () => {
    const { unmount } = renderHook(() => useSnapshot())
    await waitFor(() => expect(window.ragx.onSnapshot).toHaveBeenCalledOnce())
    unmount()
    // a funcao de unsubscribe devolvida pelo mock deve ter sido chamada
    const onSnapshotMock = vi.mocked(window.ragx.onSnapshot)
    const unsubscribe = onSnapshotMock.mock.results[0]?.value
    expect(unsubscribe).toBeDefined()
  })
})

describe('useSnapshot - corrida entre o getSnapshot inicial e o push', () => {
  const older: Snapshot = { projects: [], generatedAt: '2026-09-23T10:00:00.000Z' }
  const newer: Snapshot = { projects: [], generatedAt: '2026-09-23T10:00:05.000Z' }

  function install(getSnapshot: () => Promise<Snapshot>) {
    const listeners: Array<(s: Snapshot) => void> = []
    window.ragx = {
      ...window.ragx,
      getSnapshot: vi.fn(getSnapshot),
      onSnapshot: vi.fn((cb: (s: Snapshot) => void) => {
        listeners.push(cb)
        return () => {}
      }),
    }
    return { push: (s: Snapshot) => listeners.forEach((l) => l(s)) }
  }

  it('um getSnapshot() inicial que responde depois de um push mais novo não volta o relógio', async () => {
    let answer: (s: Snapshot) => void = () => {}
    const { push } = install(() => new Promise<Snapshot>((r) => (answer = r)))
    const { result } = renderHook(() => useSnapshot())

    act(() => push(newer))
    await act(async () => answer(older))

    expect(result.current.snapshot).toBe(newer)
  })

  it('se o inicial for mais novo que o push já recebido, vale o inicial', async () => {
    let answer: (s: Snapshot) => void = () => {}
    const { push } = install(() => new Promise<Snapshot>((r) => (answer = r)))
    const { result } = renderHook(() => useSnapshot())

    act(() => push(older))
    await act(async () => answer(newer))

    expect(result.current.snapshot).toBe(newer)
  })

  it('push sempre substitui (é o que o processo principal acabou de construir)', async () => {
    const { push } = install(async () => older)
    const { result } = renderHook(() => useSnapshot())
    await waitFor(() => expect(result.current.snapshot).toBe(older))

    act(() => push(newer))
    expect(result.current.snapshot).toBe(newer)
  })
})

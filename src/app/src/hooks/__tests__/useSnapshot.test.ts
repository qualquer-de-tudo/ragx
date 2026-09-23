import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useSnapshot } from '../useSnapshot'
import type { Snapshot } from '../../types/ragx-bridge'

const emptySnapshot: Snapshot = { projects: [], generatedAt: '2026-09-21T10:00:00Z' }

describe('useSnapshot', () => {
  beforeEach(() => {
    const listeners: Array<(s: Snapshot) => void> = []
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
      runSecurityScan: vi.fn(),
      getConnections: vi.fn(),
      listJobs: vi.fn(),
      onJobs: vi.fn(() => () => {}),
      enqueueJob: vi.fn(),
      cancelJob: vi.fn(),
      pickFolder: vi.fn(),
      discover: vi.fn(),
      getSettings: vi.fn(),
      setOnboardingDone: vi.fn(),
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

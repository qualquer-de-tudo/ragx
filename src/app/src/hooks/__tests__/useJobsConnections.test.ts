import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useJobs } from '../useJobs'
import { useConnections } from '../useConnections'
import type { ConnectionCheck, JobView, RagxBridge } from '../../types/ragx-bridge'

function bridge(over: Partial<RagxBridge> = {}): RagxBridge {
  return {
    getSnapshot: vi.fn(),
    onSnapshot: vi.fn(() => () => {}),
    getProjectStatus: vi.fn(),
    runTrial: vi.fn(),
    runSecurityScan: vi.fn(),
    getConnections: vi.fn().mockResolvedValue([]),
    listJobs: vi.fn().mockResolvedValue([]),
    onJobs: vi.fn(() => () => {}),
    enqueueJob: vi.fn(),
    cancelJob: vi.fn(),
    pickFolder: vi.fn(),
    discover: vi.fn(),
    getSettings: vi.fn(),
    setOnboardingDone: vi.fn(),
    ...over,
  }
}

const aJob = { id: 'j1', state: 'running' } as JobView
const check = { id: 'ragx', state: 'ok' } as ConnectionCheck

describe('useJobs', () => {
  it('começa com listJobs() e segue onJobs, desinscrevendo ao desmontar', async () => {
    let push: ((jobs: JobView[]) => void) | null = null
    const unsubscribe = vi.fn()
    window.ragx = bridge({
      listJobs: vi.fn().mockResolvedValue([aJob]),
      onJobs: vi.fn((cb: (jobs: JobView[]) => void) => {
        push = cb
        return unsubscribe
      }),
    })
    const { result, unmount } = renderHook(() => useJobs())
    await waitFor(() => expect(result.current).toEqual([aJob]))

    act(() => push!([]))
    expect(result.current).toEqual([])

    unmount()
    expect(unsubscribe).toHaveBeenCalledOnce()
  })

  it('um evento que chega antes do listJobs() não é sobrescrito pela lista antiga', async () => {
    let resolveList: (jobs: JobView[]) => void = () => {}
    let push: ((jobs: JobView[]) => void) | null = null
    window.ragx = bridge({
      listJobs: vi.fn(() => new Promise<JobView[]>((r) => (resolveList = r))),
      onJobs: vi.fn((cb: (jobs: JobView[]) => void) => {
        push = cb
        return () => {}
      }),
    })
    const { result } = renderHook(() => useJobs())
    const fresh = [{ ...aJob, state: 'done' } as JobView]
    act(() => push!(fresh))
    await act(async () => resolveList([aJob]))
    expect(result.current).toEqual(fresh)
  })
})

describe('useConnections', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('checa ao montar e a cada 30 s, e para ao desmontar', async () => {
    const getConnections = vi.fn().mockResolvedValue([check])
    window.ragx = bridge({ getConnections })
    const { result, unmount } = renderHook(() => useConnections())
    await act(async () => {})
    expect(getConnections).toHaveBeenCalledTimes(1)
    expect(result.current.connections).toEqual([check])

    await act(async () => vi.advanceTimersByTime(30_000))
    expect(getConnections).toHaveBeenCalledTimes(2)

    unmount()
    await act(async () => vi.advanceTimersByTime(60_000))
    expect(getConnections).toHaveBeenCalledTimes(2)
  })

  it('refresh() checa na hora', async () => {
    const getConnections = vi.fn().mockResolvedValue([check])
    window.ragx = bridge({ getConnections })
    const { result } = renderHook(() => useConnections())
    await act(async () => {})
    await act(async () => result.current.refresh())
    expect(getConnections).toHaveBeenCalledTimes(2)
  })

  it('uma falha não derruba a lista anterior', async () => {
    const getConnections = vi.fn().mockResolvedValueOnce([check]).mockRejectedValueOnce(new Error('x'))
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    window.ragx = bridge({ getConnections })
    const { result } = renderHook(() => useConnections())
    await act(async () => {})
    await act(async () => vi.advanceTimersByTime(30_000))
    expect(result.current.connections).toEqual([check])
    expect(error).toHaveBeenCalled()
    error.mockRestore()
  })
})

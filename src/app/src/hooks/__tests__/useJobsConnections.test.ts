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
    onConnections: vi.fn(() => () => {}),
    listJobs: vi.fn().mockResolvedValue([]),
    onJobs: vi.fn(() => () => {}),
    enqueueJob: vi.fn(),
    cancelJob: vi.fn(),
    pickFolder: vi.fn(),
    discover: vi.fn(),
    getSettings: vi.fn(),
    setOnboardingDone: vi.fn(),
    getOllamaEnvironment: vi.fn(),
    runOllamaBenchmark: vi.fn(),
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

  function pushable() {
    const listeners: Array<(c: ConnectionCheck[]) => void> = []
    const onConnections = vi.fn((cb: (c: ConnectionCheck[]) => void) => {
      listeners.push(cb)
      return () => {
        const i = listeners.indexOf(cb)
        if (i >= 0) listeners.splice(i, 1)
      }
    })
    return { onConnections, push: (c: ConnectionCheck[]) => listeners.forEach((l) => l(c)), listeners }
  }

  it('checa uma vez ao montar e não tem polling próprio (o processo principal é o único poller)', async () => {
    const getConnections = vi.fn().mockResolvedValue([check])
    const { onConnections } = pushable()
    window.ragx = bridge({ getConnections, onConnections })
    const { result } = renderHook(() => useConnections())
    await act(async () => {})
    expect(getConnections).toHaveBeenCalledTimes(1)
    expect(result.current.connections).toEqual([check])

    await act(async () => vi.advanceTimersByTime(120_000))
    expect(getConnections).toHaveBeenCalledTimes(1)
  })

  it('segue os resultados empurrados em ragx:connections e desinscreve ao desmontar', async () => {
    const { onConnections, push, listeners } = pushable()
    window.ragx = bridge({ onConnections })
    const { result, unmount } = renderHook(() => useConnections())
    await act(async () => {})

    const later = { id: 'ollama', state: 'warn' } as ConnectionCheck
    act(() => push([later]))
    expect(result.current.connections).toEqual([later])
    expect(result.current.checking).toBe(false)

    unmount()
    expect(listeners).toHaveLength(0)
  })

  it('a resposta do getConnections() inicial não apaga um resultado empurrado depois dela', async () => {
    let answer: (c: ConnectionCheck[]) => void = () => {}
    const getConnections = vi.fn(() => new Promise<ConnectionCheck[]>((r) => (answer = r)))
    const { onConnections, push } = pushable()
    window.ragx = bridge({ getConnections, onConnections })
    const { result } = renderHook(() => useConnections())

    const pushed = { id: 'claude', state: 'ok' } as ConnectionCheck
    act(() => push([pushed]))
    await act(async () => answer([check]))
    // As duas vêm da mesma checagem no processo principal; o que vale é o empurrado.
    expect(result.current.connections).toEqual([pushed])
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
    await act(async () => result.current.refresh())
    expect(result.current.connections).toEqual([check])
    expect(error).toHaveBeenCalled()
    error.mockRestore()
  })
})

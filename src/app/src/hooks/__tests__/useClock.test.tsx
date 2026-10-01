import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import { useClock, useLiveIds } from '../useClock'
import type { ActivityEvent } from '../../types/ragx-bridge'

const T0 = Date.parse('2026-10-01T12:00:00Z')

function ev(projectId: string, ts: number): ActivityEvent {
  return { id: `${projectId}-${ts}`, ts: new Date(ts).toISOString(), projectId, kind: 'mcp', name: 'search_hybrid' } as ActivityEvent
}

describe('useClock', () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: T0, toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('vários componentes compartilham UM setInterval e ele para quando o último sai', () => {
    const spy = vi.spyOn(globalThis, 'setInterval')
    const clear = vi.spyOn(globalThis, 'clearInterval')
    function C() {
      useClock(7_000)
      return null
    }
    const a = render(<C />)
    const b = render(<C />)
    expect(spy.mock.calls.filter((c) => c[1] === 7_000)).toHaveLength(1)
    a.unmount()
    expect(clear).not.toHaveBeenCalled()
    b.unmount()
    expect(clear).toHaveBeenCalledTimes(1)
  })

  it('o valor avança a cada intervalo', () => {
    const seen: number[] = []
    function C() {
      seen.push(useClock(9_000))
      return null
    }
    render(<C />)
    act(() => {
      vi.advanceTimersByTime(9_000)
    })
    expect(seen.at(-1)! - seen[0]).toBeGreaterThanOrEqual(9_000)
  })
})

describe('useLiveIds', () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: T0, toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('devolve o mesmo Set enquanto a pertença não muda e renderiza só quando ela muda', () => {
    const activity = [ev('a', T0)]
    const sets: Array<ReadonlySet<string>> = []
    function C() {
      sets.push(useLiveIds(activity, 5_000))
      return null
    }
    render(<C />)
    const renders = () => sets.length
    const first = sets[0]
    expect([...first]).toEqual(['a'])
    const before = renders()
    act(() => {
      vi.advanceTimersByTime(30_000)
    })
    expect(renders()).toBe(before) // 6 ticks, mesma pertença: nenhum render
    act(() => {
      vi.advanceTimersByTime(35_000)
    })
    expect(renders()).toBeGreaterThan(before)
    expect([...sets.at(-1)!]).toEqual([]) // passou de um minuto
  })
})

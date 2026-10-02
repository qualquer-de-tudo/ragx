import { describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { hasNewVersion, useUpdate } from '../useUpdate'
import { installBridge } from '../../test/snap'
import type { UpdateState } from '../../types/ragx-bridge'

const idle: UpdateState = { status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }
const available: UpdateState = { ...idle, status: 'available', version: '1.0.1' }

describe('hasNewVersion', () => {
  it('só com versão diferente da atual e em andamento ou pronta', () => {
    expect(hasNewVersion(null)).toBe(false)
    expect(hasNewVersion(idle)).toBe(false)
    expect(hasNewVersion(available)).toBe(true)
    expect(hasNewVersion({ ...available, status: 'downloading' })).toBe(true)
    expect(hasNewVersion({ ...available, status: 'downloaded' })).toBe(true)
    expect(hasNewVersion({ ...available, status: 'error' })).toBe(false)
    expect(hasNewVersion({ ...available, version: '1.0.0' })).toBe(false)
  })
})

describe('useUpdate', () => {
  it('lê o estado ao montar e acompanha o que o processo principal empurra', async () => {
    let push: (s: UpdateState) => void = () => {}
    installBridge({
      getUpdateState: vi.fn().mockResolvedValue(idle),
      onUpdate: vi.fn((cb: (s: UpdateState) => void) => {
        push = cb
        return () => {}
      }),
    })
    const { result } = renderHook(() => useUpdate())
    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).toEqual(idle))
    act(() => push(available))
    expect(result.current).toEqual(available)
  })
})

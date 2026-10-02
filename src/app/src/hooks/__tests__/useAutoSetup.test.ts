import { describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useAutoSetup } from '../useAutoSetup'
import { installBridge } from '../../test/snap'
import type { AutoSetupState } from '../../types/ragx-bridge'

const base: AutoSetupState = {
  enabled: true, running: false, lastRunAt: null,
  claude: { checked: 0, installed: [], error: null }, git: { queued: [], failed: [] },
}

describe('useAutoSetup', () => {
  it('lê o estado ao montar e acompanha o que o processo principal empurra', async () => {
    let push: (s: AutoSetupState) => void = () => {}
    installBridge({
      getAutoSetup: vi.fn().mockResolvedValue(base),
      onAutoSetup: vi.fn((cb: (s: AutoSetupState) => void) => {
        push = cb
        return () => {}
      }),
    })
    const { result } = renderHook(() => useAutoSetup())
    expect(result.current.state).toBeNull()
    await waitFor(() => expect(result.current.state).toEqual(base))
    act(() => push({ ...base, lastRunAt: '2026-10-02T12:00:00Z' }))
    expect(result.current.state?.lastRunAt).toBe('2026-10-02T12:00:00Z')
  })

  it('run marca "rodando" na hora e guarda o resultado', async () => {
    const depois = { ...base, lastRunAt: '2026-10-02T12:05:00Z' }
    const b = installBridge({ getAutoSetup: vi.fn().mockResolvedValue(base), runAutoSetup: vi.fn().mockResolvedValue(depois) })
    const { result } = renderHook(() => useAutoSetup())
    await waitFor(() => expect(result.current.state).not.toBeNull())
    act(() => result.current.run())
    expect(result.current.state?.running).toBe(true)
    await waitFor(() => expect(result.current.state).toEqual(depois))
    expect(b.runAutoSetup).toHaveBeenCalledTimes(1)
  })

  it('setEnabled grava a preferência autoSetup e atualiza o estado na hora', async () => {
    const b = installBridge({ getAutoSetup: vi.fn().mockResolvedValue(base) })
    const { result } = renderHook(() => useAutoSetup())
    await waitFor(() => expect(result.current.state).not.toBeNull())
    act(() => result.current.setEnabled(false))
    expect(result.current.state?.enabled).toBe(false)
    expect(b.setPreference).toHaveBeenCalledWith('autoSetup', false)
  })
})

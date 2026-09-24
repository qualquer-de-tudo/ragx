import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useClaudeIntegration } from '../useClaudeIntegration'

function bridge(over: Partial<Window['ragx']> = {}) {
  const b = {
    getClaudeIntegration: vi.fn().mockResolvedValue({ enabled: true }),
    setClaudeIntegration: vi.fn(),
    ...over,
  }
  window.ragx = b as unknown as Window['ragx']
  return b
}

describe('useClaudeIntegration', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('lê o estado da CLI ao montar', async () => {
    bridge({ getClaudeIntegration: vi.fn().mockResolvedValue({ enabled: false }) })
    const { result } = renderHook(() => useClaudeIntegration())
    expect(result.current.enabled).toBeNull()
    await waitFor(() => expect(result.current.enabled).toBe(false))
  })

  it('só muda quando a CLI confirma, e marca changed', async () => {
    let resolve: (v: { enabled: boolean }) => void = () => {}
    const b = bridge({ setClaudeIntegration: vi.fn(() => new Promise<{ enabled: boolean }>((r) => (resolve = r))) })
    const { result } = renderHook(() => useClaudeIntegration())
    await waitFor(() => expect(result.current.enabled).toBe(true))

    act(() => result.current.toggle())
    expect(b.setClaudeIntegration).toHaveBeenCalledWith(false)
    expect(result.current.busy).toBe(true)
    expect(result.current.enabled).toBe(true) // ainda não confirmou

    await act(async () => resolve({ enabled: false }))
    expect(result.current.enabled).toBe(false)
    expect(result.current.busy).toBe(false)
    expect(result.current.changed).toBe(true)
  })

  it('cliques enquanto troca não disparam outro pedido', async () => {
    const b = bridge({ setClaudeIntegration: vi.fn(() => new Promise<{ enabled: boolean }>(() => {})) })
    const { result } = renderHook(() => useClaudeIntegration())
    await waitFor(() => expect(result.current.enabled).toBe(true))
    act(() => result.current.toggle())
    act(() => result.current.toggle())
    expect(b.setClaudeIntegration).toHaveBeenCalledTimes(1)
  })

  it('falha mantém o estado e mostra o motivo', async () => {
    bridge({ setClaudeIntegration: vi.fn().mockRejectedValue(new Error('config ilegível')) })
    const { result } = renderHook(() => useClaudeIntegration())
    await waitFor(() => expect(result.current.enabled).toBe(true))
    await act(async () => result.current.toggle())
    expect(result.current.enabled).toBe(true)
    expect(result.current.error).toBe('config ilegível')
    expect(result.current.busy).toBe(false)
    expect(result.current.changed).toBe(false)
  })

  it('sem conseguir ler o estado, não deixa trocar', async () => {
    const b = bridge({ getClaudeIntegration: vi.fn().mockRejectedValue(new Error('x')) })
    const { result } = renderHook(() => useClaudeIntegration())
    await waitFor(() => expect(result.current.error).not.toBeNull())
    act(() => result.current.toggle())
    expect(b.setClaudeIntegration).not.toHaveBeenCalled()
  })
})

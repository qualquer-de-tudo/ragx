import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useRecheckAfterConnectionJobs } from '../useRecheckAfterConnectionJobs'
import { job } from '../../test/snap'
import type { JobView } from '../../types/ragx-bridge'

const register = job({ id: 'm', kind: 'mcp-register', label: 'Registrar o RAGX no Claude Code', projectId: null })

function setup(initial: JobView[]) {
  const refresh = vi.fn()
  const hook = renderHook(({ jobs }) => useRecheckAfterConnectionJobs(jobs, refresh), { initialProps: { jobs: initial } })
  return { ...hook, refresh }
}

describe('useRecheckAfterConnectionJobs', () => {
  it('confere de novo quando uma tarefa de conexão vista ativa termina', () => {
    const { rerender, refresh } = setup([register])
    expect(refresh).not.toHaveBeenCalled()
    rerender({ jobs: [{ ...register, state: 'done' }] })
    expect(refresh).toHaveBeenCalledTimes(1)
    // O mesmo fim não conta duas vezes.
    rerender({ jobs: [{ ...register, state: 'done' }] })
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('falha também confere de novo (o card mostra o estado real)', () => {
    const { rerender, refresh } = setup([{ ...register, state: 'queued' }])
    rerender({ jobs: [{ ...register, state: 'failed' }] })
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('tarefa que já chegou terminada, ou de projeto, não dispara nada', () => {
    const { rerender, refresh } = setup([{ ...register, state: 'done' }])
    rerender({ jobs: [{ ...register, state: 'done' }, job({ id: 'e', state: 'done' })] })
    const embed = job({ id: 'e2' })
    rerender({ jobs: [embed] })
    rerender({ jobs: [{ ...embed, state: 'done' }] })
    expect(refresh).not.toHaveBeenCalled()
  })
})

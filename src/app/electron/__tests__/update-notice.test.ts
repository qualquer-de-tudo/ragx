import { describe, expect, it, vi } from 'vitest'
import { createUpdateNotice, isNewVersion } from '../update-notice'
import type { UpdateState } from '../updater'

const state = (over: Partial<UpdateState> = {}): UpdateState => ({
  status: 'available', currentVersion: '1.0.0', version: '1.0.1', progress: null, error: null, ...over,
})

function make(notified?: string) {
  let last = notified
  const show = vi.fn()
  const remember = vi.fn((v: string) => void (last = v))
  const notice = createUpdateNotice({ notified: () => last, remember, show })
  return { notice, show, remember }
}

describe('aviso de versão nova', () => {
  it('avisa quando há uma versão diferente da atual', () => {
    const t = make()
    t.notice(state())
    expect(t.show).toHaveBeenCalledWith('1.0.1', '1.0.0')
    expect(t.remember).toHaveBeenCalledWith('1.0.1')
  })

  it('avisa uma vez por versão, mesmo com várias checagens', () => {
    const t = make()
    t.notice(state())
    t.notice(state())
    t.notice(state({ status: 'downloaded' }))
    expect(t.show).toHaveBeenCalledTimes(1)
  })

  it('avisa de novo quando sai uma versão ainda mais nova', () => {
    const t = make()
    t.notice(state())
    t.notice(state({ version: '1.0.2' }))
    expect(t.show).toHaveBeenCalledTimes(2)
  })

  it('não avisa de uma versão já avisada em outra sessão (valor gravado)', () => {
    const t = make('1.0.1')
    t.notice(state())
    expect(t.show).not.toHaveBeenCalled()
  })

  it('não avisa em checking, idle, downloading ou error, nem sem versão, nem se a versão é a mesma', () => {
    const t = make()
    for (const status of ['idle', 'checking', 'downloading', 'error'] as const) t.notice(state({ status }))
    t.notice(state({ version: null }))
    t.notice(state({ version: '1.0.0' }))
    expect(t.show).not.toHaveBeenCalled()
  })

  it('isNewVersion', () => {
    expect(isNewVersion(state())).toBe(true)
    expect(isNewVersion(state({ version: '1.0.0' }))).toBe(false)
    expect(isNewVersion(state({ version: null }))).toBe(false)
  })
})

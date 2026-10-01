import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { applyTheme, initTheme, readStoredTheme, resolveTheme, setTheme, storeTheme, watchSystemTheme, currentTheme } from '../theme'
import { installBridge } from '../test/snap'

type Listener = () => void

function mockMatchMedia(light: boolean) {
  const listeners = new Set<Listener>()
  const mq = {
    matches: light,
    addEventListener: (_: string, fn: Listener) => listeners.add(fn),
    removeEventListener: (_: string, fn: Listener) => listeners.delete(fn),
  }
  window.matchMedia = vi.fn(() => mq) as never
  return {
    mq,
    flip(next: boolean) {
      mq.matches = next
      for (const l of [...listeners]) l()
    },
    listeners,
  }
}

beforeEach(() => {
  window.localStorage.clear()
  delete document.documentElement.dataset.theme
})
afterEach(() => vi.restoreAllMocks())

describe('resolveTheme', () => {
  it('escuro e claro valem como estão; system segue o sistema', () => {
    expect(resolveTheme('dark', true)).toBe('dark')
    expect(resolveTheme('light', false)).toBe('light')
    expect(resolveTheme('system', true)).toBe('light')
    expect(resolveTheme('system', false)).toBe('dark')
  })
})

describe('armazenamento', () => {
  it('padrão escuro; guarda e lê; valor estranho volta ao padrão', () => {
    expect(readStoredTheme()).toBe('dark')
    storeTheme('light')
    expect(readStoredTheme()).toBe('light')
    window.localStorage.setItem('ragx.theme', 'roxo')
    expect(readStoredTheme()).toBe('dark')
  })

  it('localStorage lançando: leitura devolve dark e escrita não levanta', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('cheio')
    })
    expect(readStoredTheme()).toBe('dark')
    expect(() => storeTheme('light')).not.toThrow()
  })
})

describe('applyTheme e o ouvinte do sistema', () => {
  it('aplica data-theme com o tema resolvido', () => {
    mockMatchMedia(true)
    expect(applyTheme('system')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(applyTheme('dark')).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('com system, a troca do sistema reaplica; com outra preferência, não; e para de ouvir', () => {
    const m = mockMatchMedia(false)
    let pref: 'system' | 'dark' = 'system'
    const stop = watchSystemTheme(() => pref)
    m.flip(true)
    expect(document.documentElement.dataset.theme).toBe('light')
    pref = 'dark'
    applyTheme('dark')
    m.flip(false)
    m.flip(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    stop()
    expect(m.listeners.size).toBe(0)
  })

  it('sem matchMedia (ambiente sem suporte): fica escuro, sem exceção', () => {
    window.matchMedia = undefined as never
    expect(applyTheme('system')).toBe('dark')
    expect(() => watchSystemTheme(() => 'system')()).not.toThrow()
  })
})

describe('initTheme e setTheme', () => {
  it('aplica o guardado antes de perguntar ao processo principal e depois confirma pelo getSettings', async () => {
    mockMatchMedia(false)
    storeTheme('light')
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, theme: 'system' }) })
    initTheme()
    expect(document.documentElement.dataset.theme).toBe('light') // o guardado, na hora
    await vi.waitFor(() => expect(currentTheme()).toBe('system'))
    expect(document.documentElement.dataset.theme).toBe('dark') // system com sistema escuro
    expect(readStoredTheme()).toBe('system')
  })

  it('settings sem o campo: escuro (o padrão intocado)', async () => {
    mockMatchMedia(false)
    storeTheme('light')
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true }) })
    initTheme()
    await vi.waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
  })

  it('setTheme troca na hora, guarda e grava pela ponte; sem gravar quando persist é false', async () => {
    mockMatchMedia(false)
    const b = installBridge()
    await setTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(readStoredTheme()).toBe('light')
    expect(b.setTheme).toHaveBeenCalledWith('light')
    await setTheme('dark', false)
    expect(b.setTheme).toHaveBeenCalledTimes(1)
  })
})

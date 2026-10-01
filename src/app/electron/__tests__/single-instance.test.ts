import { describe, expect, it, vi } from 'vitest'
import { acquireSingleInstance, type AppLike } from '../single-instance'

function fakeApp(lock: boolean) {
  const handlers: Array<() => void> = []
  const app: AppLike = {
    requestSingleInstanceLock: vi.fn(() => lock),
    quit: vi.fn(),
    on: vi.fn((_event: 'second-instance', listener: () => void) => {
      handlers.push(listener)
    }),
  }
  return { app, handlers }
}

describe('acquireSingleInstance', () => {
  it('primeira instância: pega a trava, segue e escuta `second-instance`', () => {
    const { app, handlers } = fakeApp(true)
    const onSecond = vi.fn()
    expect(acquireSingleInstance(app, { headless: false, allowMulti: false, onSecondInstance: onSecond })).toBe(true)
    expect(app.quit).not.toHaveBeenCalled()
    handlers[0]() // outra instância tentou abrir
    expect(onSecond).toHaveBeenCalledOnce()
  })

  it('sem a trava (já há outra instância), a segunda sai e não segue', () => {
    const { app } = fakeApp(false)
    expect(acquireSingleInstance(app, { headless: false, allowMulti: false, onSecondInstance: vi.fn() })).toBe(false)
    expect(app.quit).toHaveBeenCalledOnce()
    expect(app.on).not.toHaveBeenCalled()
  })

  it('os modos sem janela do instalador NÃO pedem a trava (e nunca saem)', () => {
    const { app } = fakeApp(false) // mesmo com outra instância aberta
    expect(acquireSingleInstance(app, { headless: true, allowMulti: false, onSecondInstance: vi.fn() })).toBe(true)
    expect(app.requestSingleInstanceLock).not.toHaveBeenCalled()
    expect(app.quit).not.toHaveBeenCalled()
  })

  it('RAGX_PANEL_ALLOW_MULTI desliga a trava', () => {
    const { app } = fakeApp(false)
    expect(acquireSingleInstance(app, { headless: false, allowMulti: true, onSecondInstance: vi.fn() })).toBe(true)
    expect(app.requestSingleInstanceLock).not.toHaveBeenCalled()
  })
})

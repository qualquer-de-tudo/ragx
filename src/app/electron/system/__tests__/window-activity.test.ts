import { EventEmitter } from 'node:events'
import { describe, expect, it, vi } from 'vitest'
import { watchWindowActivity } from '../window-activity'

class FakeWindow extends EventEmitter {
  visible = true
  minimized = false
  isVisible = (): boolean => this.visible
  isMinimized = (): boolean => this.minimized
  show(): void {
    this.visible = true
    this.emit('show')
  }
  hide(): void {
    this.visible = false
    this.emit('hide')
  }
  minimize(): void {
    this.minimized = true
    this.emit('minimize')
  }
  restore(): void {
    this.minimized = false
    this.emit('restore')
  }
}

function setup() {
  const win = new FakeWindow()
  const power = new EventEmitter()
  const changes: boolean[] = []
  const dispose = watchWindowActivity(win, power, (a) => changes.push(a))
  return { win, power, changes, dispose }
}

describe('watchWindowActivity', () => {
  it('minimizar e esconder desativam; restaurar e mostrar reativam', () => {
    const { win, changes } = setup()
    win.minimize()
    win.restore()
    win.hide()
    win.show()
    expect(changes).toEqual([false, true, false, true])
  })

  it('bloquear a tela e suspender desativam', () => {
    const { power, changes } = setup()
    power.emit('lock-screen')
    power.emit('unlock-screen')
    power.emit('suspend')
    power.emit('resume')
    expect(changes).toEqual([false, true, false, true])
  })

  it('só reativa quando TODAS as condições voltam', () => {
    const { win, power, changes } = setup()
    win.minimize() // false
    power.emit('lock-screen') // continua inativo: sem aviso
    win.restore() // janela ok, tela ainda bloqueada: continua inativo
    expect(changes).toEqual([false])
    power.emit('unlock-screen') // agora sim
    expect(changes).toEqual([false, true])
    power.emit('suspend')
    win.hide()
    power.emit('resume') // acordou, mas a janela está oculta
    expect(changes).toEqual([false, true, false])
  })

  it('só avisa quando o valor MUDA (minimizar duas vezes não repete)', () => {
    const { win, changes } = setup()
    win.minimize()
    win.minimize()
    win.hide()
    expect(changes).toEqual([false])
  })

  it('começa do estado real da janela (já oculta: o primeiro evento relevante é o `show`)', () => {
    const win = new FakeWindow()
    win.visible = false
    const changes: boolean[] = []
    watchWindowActivity(win, null, (a) => changes.push(a))
    win.hide()
    expect(changes).toEqual([])
    win.show()
    expect(changes).toEqual([true])
  })

  it('a função de limpeza remove os ouvintes', () => {
    const { win, power, changes, dispose } = setup()
    dispose()
    win.minimize()
    power.emit('suspend')
    expect(changes).toEqual([])
    expect(win.listenerCount('minimize')).toBe(0)
    expect(power.listenerCount('suspend')).toBe(0)
  })

  it('funciona sem o powerMonitor (null)', () => {
    const win = new FakeWindow()
    const onChange = vi.fn()
    watchWindowActivity(win, null, onChange)
    win.minimize()
    expect(onChange).toHaveBeenCalledWith(false)
  })
})

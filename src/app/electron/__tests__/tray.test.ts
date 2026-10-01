import { describe, expect, it, vi } from 'vitest'
import { createTray, summarizeStates, trayTooltip } from '../tray'

describe('trayTooltip', () => {
  it('diz o estado em texto: em dia, defasados, com problema', () => {
    expect(trayTooltip({ ok: 12, stale: 0, problem: 0 })).toBe('RAGX: 12 em dia')
    expect(trayTooltip({ ok: 10, stale: 2, problem: 0 })).toBe('RAGX: 2 defasados, 10 em dia')
    expect(trayTooltip({ ok: 0, stale: 1, problem: 0 })).toBe('RAGX: 1 defasado')
    expect(trayTooltip({ ok: 3, stale: 0, problem: 1 })).toBe('RAGX: 1 com problema, 3 em dia')
    expect(trayTooltip({ ok: 0, stale: 0, problem: 0 })).toBe('RAGX: 0 em dia')
  })

  it('summarizeStates agrupa embeddings com defasados e indexing/no-hooks com em dia', () => {
    expect(summarizeStates(['ok', 'no-hooks', 'indexing', 'stale', 'embeddings', 'error', 'missing'])).toEqual({ ok: 3, stale: 2, problem: 2 })
  })
})

describe('createTray', () => {
  function fake() {
    const tray = { setToolTip: vi.fn(), setContextMenu: vi.fn(), on: vi.fn(), destroy: vi.fn() }
    const buildMenu = vi.fn((t: unknown) => ({ menu: t }))
    const onOpen = vi.fn()
    const onQuit = vi.fn()
    const createTrayFn = vi.fn(() => tray)
    return { tray, buildMenu, onOpen, onQuit, createTrayFn }
  }

  it('cria o ícone com "Abrir painel" e "Sair"; o clique abre o painel; update troca o texto', () => {
    const f = fake()
    const t = createTray({ createTray: f.createTrayFn, buildMenu: f.buildMenu, iconPath: 'x.png', onOpen: f.onOpen, onQuit: f.onQuit })
    expect(f.createTrayFn).toHaveBeenCalledWith('x.png')
    const labels = (f.buildMenu.mock.calls[0][0] as Array<{ label: string }>).map((i) => i.label)
    expect(labels).toEqual(['Abrir painel', 'Sair'])
    const click = f.tray.on.mock.calls[0]
    expect(click[0]).toBe('click')
    ;(click[1] as () => void)()
    expect(f.onOpen).toHaveBeenCalled()
    t.update({ ok: 1, stale: 2, problem: 0 })
    expect(f.tray.setToolTip).toHaveBeenLastCalledWith('RAGX: 2 defasados, 1 em dia')
    t.destroy()
    expect(f.tray.destroy).toHaveBeenCalled()
  })
})

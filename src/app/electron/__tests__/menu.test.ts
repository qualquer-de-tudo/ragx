import { describe, expect, it } from 'vitest'
import type { MenuItemConstructorOptions } from 'electron'
import { buildMenuTemplate } from '../menu'

function items(tpl: MenuItemConstructorOptions[]): MenuItemConstructorOptions[] {
  return tpl.flatMap((i) => [i, ...(Array.isArray(i.submenu) ? items(i.submenu) : [])])
}
const roles = (devTools: boolean) => items(buildMenuTemplate({ devTools })).map((i) => i.role)

describe('buildMenuTemplate', () => {
  it('sem devTools não há recarregar nem ferramentas do desenvolvedor', () => {
    const r = roles(false)
    for (const banned of ['reload', 'forceReload', 'toggleDevTools'] as const) expect(r).not.toContain(banned)
  })

  it('com devTools os três itens existem', () => {
    const r = roles(true)
    for (const wanted of ['reload', 'forceReload', 'toggleDevTools'] as const) expect(r).toContain(wanted)
  })

  it('edição e zoom estão sempre presentes (a RAGX-0181 testa o zoom de 200%)', () => {
    for (const devTools of [false, true]) {
      const r = roles(devTools)
      for (const wanted of ['undo', 'redo', 'cut', 'copy', 'paste', 'selectAll', 'resetZoom', 'zoomIn', 'zoomOut', 'togglefullscreen', 'quit'] as const) {
        expect(r, `${wanted} (devTools=${devTools})`).toContain(wanted)
      }
    }
  })

  it('todo rótulo é texto em português, sem travessão', () => {
    for (const devTools of [false, true]) {
      for (const i of items(buildMenuTemplate({ devTools }))) {
        if (i.type === 'separator') continue
        expect(typeof i.label).toBe('string')
        expect(i.label).not.toMatch(/—/)
        expect(i.label!.length).toBeGreaterThan(0)
      }
    }
  })
})

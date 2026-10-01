import type { ProjectState } from './project-state'

export interface StateCounts {
  ok: number
  stale: number
  problem: number
}

/** Agrupa os estados do que a bandeja diz: em dia, defasados (inclui embeddings pendentes) e com problema. */
export function summarizeStates(states: readonly ProjectState[]): StateCounts {
  const c: StateCounts = { ok: 0, stale: 0, problem: 0 }
  for (const s of states) {
    if (s === 'stale' || s === 'embeddings') c.stale += 1
    else if (s === 'missing' || s === 'error') c.problem += 1
    else c.ok += 1 // ok, no-hooks e indexing: o índice vale
  }
  return c
}

/** "RAGX: 12 em dia", "RAGX: 2 defasados", "RAGX: 1 com problema". O estado vai em texto, nunca só por cor. */
export function trayTooltip(c: StateCounts): string {
  const parts: string[] = []
  if (c.problem > 0) parts.push(`${c.problem} com problema`)
  if (c.stale > 0) parts.push(`${c.stale} ${c.stale === 1 ? 'defasado' : 'defasados'}`)
  if (c.ok > 0 || parts.length === 0) parts.push(`${c.ok} em dia`)
  return `RAGX: ${parts.join(', ')}`
}

/** O mínimo do Electron que a bandeja usa: dá para trocar por um falso nos testes. */
export interface TrayDeps {
  createTray: (iconPath: string) => TrayLike
  buildMenu: (template: Array<{ label: string; click: () => void }>) => unknown
  iconPath: string
  onOpen: () => void
  onQuit: () => void
}

export interface TrayLike {
  setToolTip: (text: string) => void
  setContextMenu: (menu: unknown) => void
  on: (event: 'click', fn: () => void) => void
  destroy: () => void
}

export interface RagxTray {
  update: (counts: StateCounts) => void
  destroy: () => void
}

/** Ícone na bandeja com o estado geral em texto, "Abrir painel" e "Sair"; o clique restaura a janela (RAGX-0191). */
export function createTray(deps: TrayDeps): RagxTray {
  const tray = deps.createTray(deps.iconPath)
  tray.setToolTip('RAGX')
  tray.setContextMenu(
    deps.buildMenu([
      { label: 'Abrir painel', click: deps.onOpen },
      { label: 'Sair', click: deps.onQuit },
    ]),
  )
  tray.on('click', deps.onOpen)
  return {
    update: (counts) => tray.setToolTip(trayTooltip(counts)),
    destroy: () => tray.destroy(),
  }
}

import type { Route } from './route'

/** Atalhos do painel, na ordem em que a ajuda os lista (RAGX-0183). Nada com Alt: no Windows ele abre a barra de menu. */
export const SHORTCUTS: ReadonlyArray<{ keys: string; what: string }> = [
  { keys: 'Ctrl K', what: 'Abrir ou fechar a paleta de comandos' },
  { keys: '/', what: 'Ir para a busca de projetos' },
  { keys: '?', what: 'Mostrar esta ajuda' },
  { keys: 'Ctrl 1', what: 'Ir para Projetos' },
  { keys: 'Ctrl 2', what: 'Ir para Atividade' },
  { keys: 'Ctrl 3', what: 'Ir para Conexões' },
  { keys: 'Ctrl 4', what: 'Ir para Como funciona' },
  { keys: 'Esc', what: 'Fechar a janela aberta' },
]

export type ShortcutAction =
  | { type: 'palette' }
  | { type: 'search' }
  | { type: 'help' }
  | { type: 'go'; route: Route }

const GO: Record<string, Route> = {
  '1': { page: 'projects' },
  '2': { page: 'activity' },
  '3': { page: 'connections' },
  '4': { page: 'how' },
}

export interface KeyLike {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
}

/**
 * O que a tecla significa. `Ctrl/Cmd+K` e `Ctrl/Cmd+1..4` valem sempre; `/` e `?` só fora de campo de texto (senão a
 * pessoa não consegue digitar "/" numa busca).
 */
export function shortcutFor(e: KeyLike, inField: boolean): ShortcutAction | null {
  if (e.altKey) return null
  const mod = e.ctrlKey || e.metaKey
  if (mod) {
    if (e.key.toLowerCase() === 'k') return { type: 'palette' }
    const route = GO[e.key]
    return route ? { type: 'go', route } : null
  }
  if (inField) return null
  if (e.key === '/') return { type: 'search' }
  if (e.key === '?') return { type: 'help' }
  return null
}

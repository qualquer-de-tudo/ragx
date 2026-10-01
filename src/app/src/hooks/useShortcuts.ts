import { useEffect } from 'react'
import { shortcutFor, type ShortcutAction } from '../shortcuts'

function inTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/**
 * Atalhos globais (`keydown` em `window`, RAGX-0183). `enabled` falso (onboarding, que não tem barra lateral) não
 * escuta nada. O ouvinte sai ao desmontar.
 */
export function useShortcuts(enabled: boolean, onAction: (action: ShortcutAction) => void): void {
  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (e: KeyboardEvent) => {
      const action = shortcutFor(e, inTextField(e.target))
      if (action === null) return
      e.preventDefault()
      onAction(action)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled, onAction])
}

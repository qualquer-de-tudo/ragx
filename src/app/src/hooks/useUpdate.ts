import { useEffect, useState } from 'react'
import type { UpdateState } from '../types/ragx-bridge'

/** Há uma versão diferente da atual pronta para baixar, baixando ou baixada? É o que acende o ponto em Preferências. */
export function hasNewVersion(state: UpdateState | null): boolean {
  if (state === null || state.version === null || state.version === state.currentVersion) return false
  return state.status === 'available' || state.status === 'downloading' || state.status === 'downloaded'
}

/** O estado da atualização do painel: lido ao montar e acompanhado pelo que o processo principal empurra em `ragx:update`. */
export function useUpdate(): UpdateState | null {
  const [state, setState] = useState<UpdateState | null>(null)

  useEffect(() => {
    let alive = true
    const off = window.ragx.onUpdate((next) => {
      if (alive) setState(next)
    })
    window.ragx.getUpdateState().then(
      (s) => {
        if (alive) setState((prev) => prev ?? s)
      },
      (err: unknown) => console.error('getUpdateState() falhou:', err),
    )
    return () => {
      alive = false
      off()
    }
  }, [])

  return state
}

import { useCallback, useEffect, useState } from 'react'
import type { Snapshot } from '../types/ragx-bridge'
import { shareSnapshot } from '../snapshotShare'
import { readCachedSnapshot, writeCachedSnapshot } from '../snapshotCache'
import { ipcErrorMessage } from '../ipcError'

function isNewer(a: Snapshot, b: Snapshot): boolean {
  return Date.parse(a.generatedAt) > Date.parse(b.generatedAt)
}

interface State {
  snapshot: Snapshot | null
  /** O que está na tela veio do cache local, não do processo principal. */
  fromCache: boolean
  /** `getSnapshot()` falhou e não há nada para mostrar. */
  error: string | null
}

export function useSnapshot(): {
  snapshot: Snapshot | null
  fromCache: boolean
  error: string | null
  retry: () => void
} {
  const [state, setState] = useState<State>(() => {
    const cached = readCachedSnapshot()
    return { snapshot: cached, fromCache: cached !== null, error: null }
  })

  /** Aplica um snapshot vivo: o cache sempre cede; entre dois vivos vale o mais novo (`generatedAt`). */
  const apply = useCallback((s: Snapshot, force: boolean) => {
    setState((prev) => {
      if (!prev.fromCache && !force && prev.snapshot !== null && !isNewer(s, prev.snapshot)) return prev
      const next = shareSnapshot(prev.snapshot, s)
      return next === prev.snapshot && !prev.fromCache && prev.error === null
        ? prev
        : { snapshot: next, fromCache: false, error: null }
    })
    writeCachedSnapshot(s)
  }, [])

  const load = useCallback(
    (isCancelled: () => boolean) => {
      window.ragx.getSnapshot().then(
        // Um push (`onSnapshot`) pode chegar antes desta resposta e ser mais novo que ela: só troca se ela for a mais nova.
        (s) => {
          if (!isCancelled()) apply(s, false)
        },
        (err) => {
          console.error('getSnapshot() falhou:', err)
          // Sem nada na tela, o erro aparece com "Tentar de novo"; com dado (cache ou vivo) a tela segue como está.
          if (!isCancelled()) setState((prev) => (prev.snapshot === null ? { ...prev, error: ipcErrorMessage(err) } : prev))
        },
      )
    },
    [apply],
  )

  useEffect(() => {
    let cancelled = false
    load(() => cancelled)
    // Sem mudança de conteúdo (só `generatedAt` novo) o estado segue o mesmo objeto: nada re-renderiza.
    const unsubscribe = window.ragx.onSnapshot((s) => apply(s, true))
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [load, apply])

  const retry = useCallback(() => {
    setState((prev) => (prev.error === null ? prev : { ...prev, error: null }))
    load(() => false)
  }, [load])

  return { snapshot: state.snapshot, fromCache: state.fromCache, error: state.error, retry }
}

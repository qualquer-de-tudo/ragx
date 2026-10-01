import { useCallback, useEffect, useSyncExternalStore } from 'react'
import type { Pricing } from '../types/ragx-bridge'
import { ipcErrorMessage } from '../ipcError'
import { notify } from '../toast'

/**
 * O preço por milhão de tokens de entrada que a pessoa informou (RAGX-0186), guardado em módulo: as três telas que
 * mostram dinheiro leem o mesmo valor e uma gravação atualiza todas. Vem de `getSettings()` e vai por `setPricing()`.
 * Sem preço (`null`), nenhuma tela mostra valor em dinheiro.
 */
interface State {
  pricing: Pricing | null
  status: 'idle' | 'loading' | 'ready'
}

let state: State = { pricing: null, status: 'idle' }
const listeners = new Set<() => void>()

function set(next: State) {
  state = next
  for (const l of [...listeners]) l()
}

function load() {
  if (state.status !== 'idle') return
  set({ ...state, status: 'loading' })
  // `Promise.resolve().then` também transforma um throw síncrono (ponte ausente) em rejeição.
  Promise.resolve()
    .then(() => window.ragx.getSettings())
    .then(
    // Uma gravação que terminou antes da leitura manda: a leitura atrasada não a desfaz.
    (s) => state.status !== 'ready' && set({ pricing: s.pricing ?? null, status: 'ready' }),
    (err: unknown) => {
      console.error('getSettings() falhou ao ler o preço:', err)
      set({ ...state, status: 'ready' })
    },
  )
}

/** Volta ao estado inicial (testes). */
export function resetPricing(): void {
  set({ pricing: null, status: 'idle' })
}

export function usePricing(): { pricing: Pricing | null; save: (next: Pricing | null) => Promise<boolean> } {
  const snapshot = useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => state,
    () => state,
  )
  useEffect(() => {
    load()
  }, [])

  const save = useCallback(async (next: Pricing | null) => {
    try {
      await window.ragx.setPricing(next)
      set({ pricing: next, status: 'ready' })
      return true
    } catch (err) {
      console.error('setPricing() falhou:', err)
      notify.error(`Não foi possível salvar o preço: ${ipcErrorMessage(err)}`)
      return false
    }
  }, [])

  return { pricing: snapshot.pricing, save }
}

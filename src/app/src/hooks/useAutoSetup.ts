import { useCallback, useEffect, useRef, useState } from 'react'
import type { AutoSetupState } from '../types/ragx-bridge'

export interface AutoSetupView {
  /** `null` até a primeira resposta do processo principal. */
  state: AutoSetupState | null
  /** Roda o ajuste agora ("Ajustar agora"); o resultado chega também por `onAutoSetup`. */
  run: () => void
  /** Liga ou desliga a preferência `autoSetup`. */
  setEnabled: (enabled: boolean) => void
}

/**
 * O ajuste automático dos hooks (Claude Code e git): estado, "ajustar agora" e o interruptor. O processo principal
 * é quem roda; aqui só se lê o estado ao montar e se escuta o que ele empurra em `ragx:autoSetup`.
 */
export function useAutoSetup(): AutoSetupView {
  const [state, setState] = useState<AutoSetupState | null>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    const unsubscribe = window.ragx.onAutoSetup((next) => {
      if (alive.current) setState(next)
    })
    window.ragx.getAutoSetup().then(
      (s) => {
        if (alive.current) setState((prev) => prev ?? s)
      },
      (err: unknown) => console.error('getAutoSetup() falhou:', err),
    )
    return () => {
      alive.current = false
      unsubscribe()
    }
  }, [])

  const run = useCallback(() => {
    setState((prev) => (prev === null ? prev : { ...prev, running: true }))
    window.ragx.runAutoSetup().then(
      (s) => {
        if (alive.current) setState(s)
      },
      (err: unknown) => {
        console.error('runAutoSetup() falhou:', err)
        if (alive.current) setState((prev) => (prev === null ? prev : { ...prev, running: false }))
      },
    )
  }, [])

  const setEnabled = useCallback((enabled: boolean) => {
    setState((prev) => (prev === null ? prev : { ...prev, enabled }))
    window.ragx.setPreference('autoSetup', enabled).catch((err: unknown) => {
      console.error('setPreference(autoSetup) falhou:', err)
      void window.ragx.getAutoSetup().then((s) => alive.current && setState(s))
    })
  }, [])

  return { state, run, setEnabled }
}

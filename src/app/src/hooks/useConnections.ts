import { useCallback, useEffect, useRef, useState } from 'react'
import type { ConnectionCheck } from '../types/ragx-bridge'

export const CONNECTIONS_INTERVAL_MS = 30_000

/**
 * Checagem das três conexões (RAGX CLI, Claude Code, Ollama): ao montar e a
 * cada 30 s. `refresh()` checa na hora (botão "Verificar agora").
 * `connections` é `null` até a primeira resposta; uma falha mantém a lista
 * anterior em vez de apagar o que já se sabia.
 */
export function useConnections(): {
  connections: ConnectionCheck[] | null
  checking: boolean
  refresh: () => Promise<void>
} {
  const [connections, setConnections] = useState<ConnectionCheck[] | null>(null)
  // Começa `true`: a primeira checagem sai assim que o hook monta.
  const [checking, setChecking] = useState(true)
  const alive = useRef(true)

  // Só muda estado nos retornos da promessa, então pode ser chamada no corpo
  // do efeito sem cair em react-hooks/set-state-in-effect.
  const check = useCallback(
    () =>
      window.ragx.getConnections().then(
        (next) => {
          if (!alive.current) return
          setConnections(next)
          setChecking(false)
        },
        (err: unknown) => {
          if (!alive.current) return
          console.error('getConnections() falhou:', err)
          setChecking(false)
        },
      ),
    [],
  )

  const refresh = useCallback(async () => {
    setChecking(true)
    await check()
  }, [check])

  useEffect(() => {
    alive.current = true
    void check()
    const timer = window.setInterval(() => void check(), CONNECTIONS_INTERVAL_MS)
    return () => {
      alive.current = false
      window.clearInterval(timer)
    }
  }, [check])

  return { connections, checking, refresh }
}

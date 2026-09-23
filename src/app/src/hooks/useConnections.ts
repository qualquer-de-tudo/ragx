import { useCallback, useEffect, useRef, useState } from 'react'
import type { ConnectionCheck } from '../types/ragx-bridge'

/**
 * Checagem das três conexões (RAGX CLI, Claude Code, Ollama). O processo
 * principal é o único poller: confere a cada 30 s, no startup e quando
 * termina uma correção de conexão, e empurra cada resultado em
 * `ragx:connections` (`onConnections`). Aqui só se pede uma checagem ao
 * montar (o processo principal junta com a do startup, se ainda estiver
 * rodando) e no `refresh()` do botão "Verificar agora".
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
  // Um resultado empurrado já chegou: a resposta da checagem de montagem
  // não pode passar por cima dele.
  const pushed = useRef(false)

  // Só muda estado nos retornos da promessa, então pode ser chamada no corpo
  // do efeito sem cair em react-hooks/set-state-in-effect.
  const check = useCallback(
    (fromMount: boolean) =>
      window.ragx.getConnections().then(
        (next) => {
          if (!alive.current) return
          if (!(fromMount && pushed.current)) setConnections(next)
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
    await check(false)
  }, [check])

  useEffect(() => {
    alive.current = true
    const unsubscribe = window.ragx.onConnections((next) => {
      pushed.current = true
      setConnections(next)
      setChecking(false)
    })
    void check(true)
    return () => {
      alive.current = false
      unsubscribe()
    }
  }, [check])

  return { connections, checking, refresh }
}

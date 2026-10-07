import { useCallback, useEffect, useRef, useState } from 'react'
import type { McpClientId, McpIntegration } from '../types/ragx-bridge'
import { ipcErrorMessage } from '../ipcError'

/** Lê ao abrir Conexões e sob demanda; não cria um poller por agente. */
export function useMcpIntegrations(refreshKey = 0) {
  const [clients, setClients] = useState<McpIntegration[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<McpClientId | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [changed, setChanged] = useState<ReadonlySet<McpClientId>>(new Set())
  const alive = useRef(true)
  const sequence = useRef(0)
  const changing = useRef(false)

  const read = useCallback(async () => {
    if (changing.current) return
    const revision = ++sequence.current
    try {
      const result = await window.ragx.getMcpIntegrations()
      if (alive.current && sequence.current === revision) { setClients(result); setError(null) }
    } catch (err) {
      if (alive.current && sequence.current === revision) setError(ipcErrorMessage(err))
    } finally {
      if (alive.current && sequence.current === revision) setLoading(false)
    }
  }, [])

  useEffect(() => {
    alive.current = true
    const revision = ++sequence.current
    if (!changing.current) {
      window.ragx.getMcpIntegrations().then((result) => {
        if (alive.current && sequence.current === revision) { setClients(result); setError(null) }
      }, (err: unknown) => {
        if (alive.current && sequence.current === revision) setError(ipcErrorMessage(err))
      }).finally(() => {
        if (alive.current && sequence.current === revision) setLoading(false)
      })
    }
    return () => { alive.current = false; sequence.current += 1 }
  }, [read, refreshKey])

  const refresh = useCallback(() => {
    if (changing.current) return
    setLoading(true)
    void read()
  }, [read])

  const setEnabled = useCallback(async (id: McpClientId, enabled: boolean) => {
    if (changing.current) return
    changing.current = true
    sequence.current += 1
    setBusy(id)
    setError(null)
    try {
      const result = await window.ragx.setMcpIntegration(id, enabled)
      if (!alive.current) return
      setClients(result)
      setChanged((current) => new Set([...current, id]))
    } catch (err) {
      if (alive.current) setError(ipcErrorMessage(err))
    } finally {
      changing.current = false
      if (alive.current) { setBusy(null); setLoading(false) }
    }
  }, [])

  return { clients, loading, busy, error, changed, refresh, setEnabled }
}

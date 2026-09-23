import { useEffect, useRef } from 'react'
import type { JobKind, JobView } from '../types/ragx-bridge'

const CONNECTION_KINDS: readonly JobKind[] = ['mcp-register', 'ollama-start', 'ollama-pull']

/**
 * Confere as conexões de novo assim que termina (bem ou mal) uma tarefa de
 * conexão que este painel viu na fila ou rodando: quem clicou em "Registrar"
 * vê o card mudar na hora, não 30 s depois.
 */
export function useRecheckAfterConnectionJobs(jobs: readonly JobView[], refresh: () => unknown): void {
  const active = useRef(new Set<string>())

  useEffect(() => {
    const seen = new Set<string>()
    let finished = false
    for (const j of jobs) {
      if (!CONNECTION_KINDS.includes(j.kind)) continue
      seen.add(j.id)
      if (j.state === 'queued' || j.state === 'running') active.current.add(j.id)
      else if (active.current.delete(j.id)) finished = true
    }
    // Tarefa que saiu da lista sem ser vista terminar: esquece.
    for (const id of active.current) if (!seen.has(id)) active.current.delete(id)
    if (finished) refresh()
  }, [jobs, refresh])
}

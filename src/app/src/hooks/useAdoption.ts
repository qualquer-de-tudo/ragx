import { useEffect, useState } from 'react'
import type { ActivityEvent, AdoptionSummary } from '../types/ragx-bridge'

/**
 * Adoção pelos agentes (RAGX-0190): busca no mount e de novo quando chega evento novo de tipo `session` ou `mcp`.
 * `null` enquanto não há resposta (ou se a leitura falhar: a seção some, a tela segue).
 */
export function useAdoption(events: readonly ActivityEvent[]): AdoptionSummary | null {
  const [summary, setSummary] = useState<AdoptionSummary | null>(null)
  // Chave do último evento que muda a razão: sem ele, o hook não busca de novo.
  const latest = events.find((e) => e.kind === 'session' || e.kind === 'mcp')?.id ?? null

  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => window.ragx.getAdoption())
      .then(
        (s) => {
          if (!cancelled) setSummary(s)
        },
        (err: unknown) => console.error('getAdoption() falhou:', err),
      )
    return () => {
      cancelled = true
    }
  }, [latest])

  return summary
}

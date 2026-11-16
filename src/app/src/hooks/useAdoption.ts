import { useEffect, useState } from 'react'
import type { ActivityEvent, AdoptionSummary } from '../types/ragx-bridge'
import { isRagxUse } from '../../electron/data/ragx-use'

/**
 * Adoção pelos agentes (RAGX-0190): busca no mount e de novo quando chega `session_start` ou uso do RAGX (`isRagxUse`).
 * `null` enquanto não há resposta (ou se a leitura falhar: a seção some, a tela segue).
 */
export function useAdoption(events: readonly ActivityEvent[]): AdoptionSummary | null {
  const [summary, setSummary] = useState<AdoptionSummary | null>(null)
  // Chave do último evento que muda a razão: sem ele, o hook não busca de novo.
  const latest = events.find((e) => e.kind === 'session' || isRagxUse(e))?.id ?? null

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

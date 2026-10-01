import { useEffect, useState } from 'react'
import type { Snapshot } from '../types/ragx-bridge'
import { shareSnapshot } from '../snapshotShare'

function isNewer(a: Snapshot, b: Snapshot): boolean {
  return Date.parse(a.generatedAt) > Date.parse(b.generatedAt)
}

export function useSnapshot(): { snapshot: Snapshot | null } {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)

  useEffect(() => {
    let cancelled = false
    window.ragx.getSnapshot().then(
      (s) => {
        // Um push (`onSnapshot`) pode chegar antes desta resposta e ser mais
        // novo que ela: só troca se a resposta inicial for mesmo a mais nova.
        if (!cancelled) setSnapshot((prev) => (prev === null || isNewer(s, prev) ? shareSnapshot(prev, s) : prev))
      },
      (err) => {
        // Sem isso, uma rejeicao deixa `snapshot` preso em null para sempre
        // e a UI mostra "nenhum projeto no hub ainda" mesmo quando o hub tem
        // projetos reais (ver Finding 2 da revisao final).
        if (!cancelled) console.error('getSnapshot() falhou:', err)
      },
    )
    // Sem mudança de conteúdo (só `generatedAt` novo) o estado segue o mesmo objeto: nada re-renderiza.
    const unsubscribe = window.ragx.onSnapshot((s) => setSnapshot((prev) => shareSnapshot(prev, s)))
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  return { snapshot }
}

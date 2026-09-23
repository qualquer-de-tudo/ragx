import { useEffect, useState } from 'react'
import type { JobView } from '../types/ragx-bridge'

/** Fila de tarefas: começa com `listJobs()` e segue os eventos de `onJobs`. */
export function useJobs(): JobView[] {
  const [jobs, setJobs] = useState<JobView[]>([])

  useEffect(() => {
    let cancelled = false
    // Um evento de `onJobs` que chegue antes da resposta de `listJobs()` é
    // mais novo que ela; a lista inicial não pode sobrescrevê-lo.
    let pushed = false
    const unsubscribe = window.ragx.onJobs((next) => {
      pushed = true
      setJobs(next)
    })
    window.ragx.listJobs().then(
      (initial) => {
        if (!cancelled && !pushed) setJobs(initial)
      },
      (err) => {
        if (!cancelled) console.error('listJobs() falhou:', err)
      },
    )
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  return jobs
}

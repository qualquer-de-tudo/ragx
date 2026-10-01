import { useEffect, useRef } from 'react'
import type { JobState, JobView } from '../types/ragx-bridge'
import { notify } from '../toast'

/**
 * Avisa quando uma tarefa passa a `failed` (RAGX-0180): a fila mostra "falhou" no painel de tarefas, mas quem está em
 * outra tela nunca via. A primeira lista com tarefas só serve de ponto de partida (o que já tinha falhado antes de a
 * janela abrir não avisa), e `cancelled` nunca avisa.
 */
export function useJobFailureToasts(jobs: readonly JobView[]): void {
  const known = useRef<Map<string, JobState> | null>(null)
  useEffect(() => {
    const prev = known.current
    if (prev === null && jobs.length === 0) return // a lista inicial vazia não é "a primeira lista"
    if (prev !== null) {
      for (const j of jobs) {
        if (j.state === 'failed' && prev.get(j.id) !== 'failed') {
          notify.error(j.error ? `${j.label}: falhou. ${j.error}` : `${j.label}: falhou.`)
        }
      }
    }
    known.current = new Map(jobs.map((j) => [j.id, j.state]))
  }, [jobs])
}

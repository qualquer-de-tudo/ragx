import type { JobKind, JobView } from './types/ragx-bridge'

/** Enfileira uma tarefa de projeto pelo tipo e id; falha vai para o console. */
export function enqueue(kind: JobKind, projectId: string): Promise<JobView | null> {
  return window.ragx.enqueueJob({ kind, projectId }).catch((err: unknown) => {
    console.error(`enqueueJob(${kind}) falhou:`, err)
    return null
  })
}

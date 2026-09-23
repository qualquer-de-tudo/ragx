import type { ConnectionAction, JobKind, JobView } from './types/ragx-bridge'

/** Enfileira uma tarefa de projeto pelo tipo e id; falha vai para o console. */
export function enqueue(kind: JobKind, projectId: string): Promise<JobView | null> {
  return window.ragx.enqueueJob({ kind, projectId }).catch((err: unknown) => {
    console.error(`enqueueJob(${kind}) falhou:`, err)
    return null
  })
}

/** Enfileira a ação de um card de conexão (o modelo só vai quando existe). */
export function enqueueConnectionAction(action: ConnectionAction): Promise<JobView | null> {
  // Medir velocidade não é tarefa da fila: chama o benchmark direto (o card
  // é atualizado pela checagem de conexões seguinte).
  if (action.kind === 'ollama-benchmark') {
    return window.ragx.runOllamaBenchmark().then(
      () => null,
      (err: unknown) => {
        console.error('runOllamaBenchmark() falhou:', err)
        return null
      },
    )
  }
  const req = action.model === undefined ? { kind: action.kind } : { kind: action.kind, model: action.model }
  return window.ragx.enqueueJob(req).catch((err: unknown) => {
    console.error(`enqueueJob(${action.kind}) falhou:`, err)
    return null
  })
}

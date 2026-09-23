import type { ConnectionAction, JobKind, JobView } from './types/ragx-bridge'

/** Enfileira uma tarefa de projeto pelo tipo e id; falha vai para o console. */
export function enqueue(kind: JobKind, projectId: string): Promise<JobView | null> {
  return window.ragx.enqueueJob({ kind, projectId }).catch((err: unknown) => {
    console.error(`enqueueJob(${kind}) falhou:`, err)
    return null
  })
}

/**
 * Mede a velocidade do Ollama e, com a medição feita (dando certo ou não),
 * pede uma checagem de conexões: o processo principal guarda a última medição
 * e a põe nos fatos do card, e publica o resultado em `ragx:connections`.
 * Nunca rejeita: devolve a mensagem de erro para o card mostrar, ou `null`.
 */
export async function measureOllama(): Promise<string | null> {
  let error: string | null = null
  try {
    const result = await window.ragx.runOllamaBenchmark()
    if (!result.ok) error = result.error ?? 'erro desconhecido'
  } catch (err) {
    console.error('runOllamaBenchmark() falhou:', err)
    error = err instanceof Error ? err.message : String(err)
  }
  try {
    await window.ragx.getConnections()
  } catch (err) {
    console.error('getConnections() depois da medição falhou:', err)
  }
  return error
}

/** Enfileira a ação de um card de conexão (o modelo só vai quando existe). */
export function enqueueConnectionAction(action: ConnectionAction): Promise<JobView | null> {
  // Medir velocidade não é tarefa da fila: mede direto e pede a checagem
  // nova. O card chama `measureOllama` ele mesmo para mostrar "Medindo…" e o
  // erro; aqui é só o caminho de quem não precisa disso.
  if (action.kind === 'ollama-benchmark') {
    return measureOllama().then(() => null)
  }
  const req = action.model === undefined ? { kind: action.kind } : { kind: action.kind, model: action.model }
  return window.ragx.enqueueJob(req).catch((err: unknown) => {
    console.error(`enqueueJob(${action.kind}) falhou:`, err)
    return null
  })
}

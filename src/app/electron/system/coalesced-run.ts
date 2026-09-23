/**
 * Uma execução por vez de uma tarefa assíncrona (ex.: a checagem de conexões).
 *
 * - `join()`: junta-se à execução em andamento, ou começa uma.
 * - `fresh()`: o resultado precisa refletir algo que aconteceu AGORA (ex.: uma
 *   tarefa do Ollama acabou de terminar). Com uma execução em andamento, que
 *   começou antes, agenda exatamente MAIS UMA para depois dela; várias
 *   chamadas no meio da mesma execução dividem essa extra. Nunca vira laço:
 *   a extra só existe porque alguém pediu `fresh()`.
 */
export function createCoalescedRun<T>(task: () => Promise<T>): { join: () => Promise<T>; fresh: () => Promise<T> } {
  let inFlight: Promise<T> | null = null
  let extra: Promise<T> | null = null

  function start(): Promise<T> {
    // Começa na hora (não num microtask depois); um `throw` síncrono vira rejeição.
    let started: Promise<T>
    try {
      started = task()
    } catch (err) {
      started = Promise.reject(err)
    }
    const run: Promise<T> = started.finally(() => {
      if (inFlight === run) inFlight = null
    })
    inFlight = run
    return run
  }

  function join(): Promise<T> {
    return inFlight ?? start()
  }

  function fresh(): Promise<T> {
    const current = inFlight
    if (current === null) return start()
    if (extra !== null) return extra
    const next: Promise<T> = current
      .then(
        () => undefined,
        () => undefined,
      )
      .then(() => {
        extra = null
        // Alguém pode ter começado uma execução depois da antiga: também serve.
        return join()
      })
    extra = next
    return next
  }

  return { join, fresh }
}

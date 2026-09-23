import type { JobKind, JobView } from '../../src/types/ragx-bridge'

const TERMINAL: ReadonlySet<JobView['state']> = new Set(['done', 'failed', 'cancelled'])

/** Tarefas que corrigem uma conexão: quando terminam, o processo principal confere as conexões de novo. */
export const CONNECTION_JOB_KINDS: ReadonlySet<JobKind> = new Set<JobKind>(['mcp-register', 'ollama-start', 'ollama-pull'])

/**
 * Tarefas que acabaram de chegar a um estado final: estavam em `previous`
 * com outro estado e agora estão `done`/`failed`/`cancelled`. Uma tarefa
 * que aparece pela primeira vez já terminada não conta (não foi vista rodar).
 */
export function justFinishedJobs(previous: ReadonlyMap<string, JobView['state']>, jobs: readonly JobView[]): JobView[] {
  return jobs.filter((j) => {
    const prev = previous.get(j.id)
    return prev !== undefined && prev !== j.state && TERMINAL.has(j.state)
  })
}

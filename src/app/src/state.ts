import type { ConnectionAction, JobKind, JobView, ProjectSnapshot } from './types/ragx-bridge'

export type ProjectState = 'missing' | 'indexing' | 'error' | 'embeddings' | 'stale' | 'no-hooks' | 'ok'

/**
 * Deriva o estado de um projeto a partir do snapshot e da fila de tarefas em
 * andamento (`busyIds`, Task 5). A ordem das regras importa: a primeira que
 * casar vence.
 */
export function deriveProjectState(p: ProjectSnapshot, busyIds: ReadonlySet<string>): ProjectState {
  if (!p.exists) return 'missing'
  if (p.running !== null || busyIds.has(p.id)) return 'indexing'
  if (p.counts === null || p.lastError !== null) return 'error'
  if (p.counts.pendingEmbeddings > 0) return 'embeddings'
  if (p.index === null) return 'stale'
  if (
    p.git &&
    (p.index.commit !== p.git.commit ||
      (p.index.branch !== null && p.git.branch !== null && p.index.branch !== p.git.branch))
  ) {
    return 'stale'
  }
  if (p.hooksInstalled === false) return 'no-hooks'
  return 'ok'
}

export const STATE_LABEL: Record<ProjectState, string> = {
  missing: 'Pasta ausente',
  indexing: 'Indexando…',
  error: 'Com problema',
  embeddings: 'Embeddings faltando',
  stale: 'Defasado',
  'no-hooks': 'Sem hooks',
  ok: 'Atualizado',
}

export const STATE_TONE: Record<ProjectState, 'good' | 'warning' | 'critical' | 'accent' | 'muted'> = {
  missing: 'critical',
  indexing: 'accent',
  error: 'critical',
  embeddings: 'warning',
  stale: 'warning',
  'no-hooks': 'muted',
  ok: 'good',
}

export const STATE_ACTION: Record<ProjectState, { kind: JobKind | 'open'; label: string } | null> = {
  missing: null,
  indexing: null,
  error: { kind: 'open', label: 'Ver detalhes' },
  embeddings: { kind: 'embed', label: 'Gerar embeddings' },
  stale: { kind: 'update', label: 'Atualizar agora' },
  'no-hooks': { kind: 'hooks-install', label: 'Instalar hooks' },
  ok: { kind: 'open', label: 'Abrir' },
}

export function isOutdated(s: ProjectState): boolean {
  return s === 'stale' || s === 'embeddings'
}

export function hasProblem(s: ProjectState): boolean {
  return s === 'missing' || s === 'error'
}

/** Tarefas que indexam o projeto (mexem no índice): só elas deixam o selo "Indexando…". */
const INDEX_KINDS: readonly JobKind[] = ['add-project', 'update', 'embed', 'reindex-full']

/**
 * Ids dos projetos com tarefa de indexação na fila ou rodando: o `busyIds` de
 * `deriveProjectState`. Sync, grafo, dicionário e hooks não contam: o índice
 * continua valendo enquanto rodam (o botão de cada um já diz "Na fila"/"Rodando").
 */
export function busyProjectIds(jobs: readonly JobView[]): Set<string> {
  return new Set(
    jobs
      .filter((j) => INDEX_KINDS.includes(j.kind) && (j.state === 'queued' || j.state === 'running'))
      .flatMap((j) => (j.projectId === null ? [] : [j.projectId])),
  )
}

/**
 * Tarefa na fila ou rodando deste projeto, de um dos tipos pedidos: é o que
 * deixa um botão de ação "Na fila" ou "Rodando" (a rodando tem prioridade).
 */
export function activeJobFor(jobs: readonly JobView[], projectId: string, kinds: readonly JobKind[]): JobView | null {
  const mine = jobs.filter(
    (j) => j.projectId === projectId && kinds.includes(j.kind) && (j.state === 'queued' || j.state === 'running'),
  )
  return mine.find((j) => j.state === 'running') ?? mine[0] ?? null
}

export function jobStateLabel(j: JobView): string {
  return j.state === 'running' ? 'Rodando' : 'Na fila'
}

/** Chunks que ainda não têm embedding (0 sem contagens). */
export function missingEmbeddings(counts: ProjectSnapshot['counts']): number {
  if (counts === null) return 0
  return Math.max(counts.pendingEmbeddings, counts.chunks - counts.embeddings, 0)
}

/**
 * Tarefa na fila ou rodando para uma ação de conexão (a rodando tem
 * prioridade). `ollama-pull` só conta se for do mesmo modelo.
 */
export function activeConnectionJob(jobs: readonly JobView[], action: ConnectionAction): JobView | null {
  const mine = jobs.filter(
    (j) =>
      j.kind === action.kind &&
      (j.state === 'queued' || j.state === 'running') &&
      (action.kind !== 'ollama-pull' || j.model === (action.model ?? null)),
  )
  return mine.find((j) => j.state === 'running') ?? mine[0] ?? null
}

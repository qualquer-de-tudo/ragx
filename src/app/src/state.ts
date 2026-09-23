import type { ProjectSnapshot } from './types/ragx-bridge'

export type ProjectState = 'missing' | 'indexing' | 'error' | 'embeddings' | 'stale' | 'no-hooks' | 'ok'

/**
 * Subconjunto do catálogo de tarefas (`ragx-bridge.d.ts`, Task 5/6) usado só
 * para tipar o botão de ação de cada selo de estado nesta tarefa. Quando a
 * Task 6 reescrever `ragx-bridge.d.ts` com o `JobKind` completo (mesmos 13
 * valores, ver global-constraints.md), troque este alias local pelo import
 * de lá.
 */
type JobKind =
  | 'add-project'
  | 'update'
  | 'embed'
  | 'reindex-full'
  | 'sync'
  | 'graph'
  | 'dictionary'
  | 'hooks-install'
  | 'hooks-uninstall'
  | 'remove-from-hub'
  | 'mcp-register'
  | 'ollama-start'
  | 'ollama-pull'

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

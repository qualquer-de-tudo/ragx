import type { JobKind, JobView, ProjectSnapshot } from '../src/types/ragx-bridge'

/**
 * A regra de `deriveProjectState` e `busyProjectIds` de `src/state.ts`, portada para o processo principal (RAGX-0191):
 * o `tsconfig.electron.json` tem `rootDir: electron` e o main não importa de `src/` em tempo de execução. Um teste de
 * paridade (`project-state.test.ts`) compara as duas para toda combinação de fixtures: mudou lá, mude aqui.
 */
export type ProjectState = 'missing' | 'indexing' | 'error' | 'embeddings' | 'stale' | 'no-hooks' | 'ok'

const INDEX_KINDS: readonly JobKind[] = ['add-project', 'update', 'embed', 'reindex-full']

export function busyProjectIds(jobs: readonly JobView[]): Set<string> {
  return new Set(
    jobs
      .filter((j) => INDEX_KINDS.includes(j.kind) && (j.state === 'queued' || j.state === 'running'))
      .flatMap((j) => (j.projectId === null ? [] : [j.projectId])),
  )
}

export function deriveProjectState(p: ProjectSnapshot, busyIds: ReadonlySet<string>): ProjectState {
  if (!p.exists) return 'missing'
  if (p.running !== null || busyIds.has(p.id)) return 'indexing'
  if (p.lastError !== null) return 'error'
  // Sem `status.json` (RAGX-0176) o painel não tem números: defasado, com a ação de atualizar.
  if (p.counts === null) return 'stale'
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

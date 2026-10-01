import { describe, expect, it } from 'vitest'
import { busyProjectIds as busyMain, deriveProjectState as deriveMain } from '../project-state'
import { busyProjectIds, deriveProjectState } from '../../src/state'
import { job, snap } from '../../src/test/snap'
import type { JobKind, JobView, ProjectSnapshot } from '../../src/types/ragx-bridge'

// RAGX-0191: a regra do processo principal é a de `src/state.ts`. Para toda combinação das fixtures, as duas dão o mesmo.
const counts = (over: Partial<NonNullable<ProjectSnapshot['counts']>> = {}) => ({ documents: 1, chunks: 10, embeddings: 10, pendingEmbeddings: 0, ...over })

const FIXTURES: Array<[string, ProjectSnapshot]> = [
  ['em dia', snap()],
  ['sem índice', snap({ index: null })],
  ['sem contagem (sem status.json)', snap({ counts: null })],
  ['commit diferente', snap({ git: { branch: 'main', commit: 'c2' } })],
  ['branch diferente', snap({ git: { branch: 'feat/x', commit: 'c1' } })],
  ['sem git', snap({ git: null })],
  ['embeddings pendentes', snap({ counts: counts({ pendingEmbeddings: 5 }) })],
  ['rodando', snap({ running: { source: 'cli', startedAt: '2026-10-01T10:00:00Z' } })],
  ['pasta ausente', snap({ exists: false })],
  ['com erro', snap({ lastError: 'x' })],
  ['sem hooks', snap({ hooksInstalled: false })],
  ['hooks desconhecidos', snap({ hooksInstalled: null })],
]

const JOBS: Array<[string, JobView[]]> = [
  ['sem tarefas', []],
  ...(['update', 'embed', 'add-project', 'reindex-full', 'graph', 'hooks-install', 'sync', 'dictionary'] as JobKind[]).flatMap((kind) =>
    (['queued', 'running', 'done', 'failed'] as const).map((state): [string, JobView[]] => [`${kind} ${state}`, [job({ kind, state, projectId: 'p1' })]]),
  ),
  ['tarefa de outro projeto', [job({ kind: 'update', state: 'running', projectId: 'outro' })]],
]

describe('paridade entre electron/project-state.ts e src/state.ts', () => {
  for (const [fname, project] of FIXTURES) {
    for (const [jname, jobs] of JOBS) {
      it(`${fname} x ${jname}`, () => {
        expect(deriveMain(project, busyMain(jobs))).toBe(deriveProjectState(project, busyProjectIds(jobs)))
        expect([...busyMain(jobs)].sort()).toEqual([...busyProjectIds(jobs)].sort())
      })
    }
  }
})

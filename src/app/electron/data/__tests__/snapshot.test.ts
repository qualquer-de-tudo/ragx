import { describe, expect, it, vi } from 'vitest'
import { buildSnapshot, type SnapshotDeps } from '../snapshot'
import type { HubProject } from '../types'
import type { StatusFile } from '../status-file'
import type { GitHead } from '../git'

function project(over: Partial<HubProject> = {}): HubProject {
  return {
    id: 'p1',
    name: 'p1',
    path: 'C:/p1',
    cloned: true,
    embeddingModel: 'nomic-embed-text',
    visibility: 'workspace',
    status: 'ok',
    chunks: 10,
    lastSync: null,
    ...over,
  }
}

function statusFile(over: Partial<StatusFile> = {}): StatusFile {
  return {
    schema_version: 1,
    written_at: '2026-09-23T10:00:00Z',
    project: { id: 'p1', name: 'p1', root: 'C:/p1' },
    index: {
      finished_at: '2026-09-23T09:00:00Z',
      mode: 'incremental',
      source: 'cli',
      branch: 'main',
      commit: 'c1',
      dirty: false,
    },
    counts: { documents: 4, chunks: 10, embeddings: 8, pending_embeddings: 2 },
    embedding: { provider: 'ollama', model: 'nomic-embed-text' },
    hooks: { installed: true },
    running: null,
    pending: false,
    last_error: null,
    ...over,
  }
}

function baseDeps(over: Partial<SnapshotDeps> = {}): SnapshotDeps {
  return {
    readRegistry: () => [project()],
    readStatus: () => null,
    readStats: () => ({ documents: 1, chunks: 2, embeddings: 1 }),
    readTelemetry: () => ({ callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null }),
    readGit: async () => ({ branch: 'main', commit: 'c1' }),
    exists: () => true,
    isPidAlive: () => true,
    ...over,
  }
}

describe('buildSnapshot', () => {
  it('(a) projeto com status.json usa as contagens e o index dele', async () => {
    const snap = await buildSnapshot(baseDeps({ readStatus: () => statusFile() }))
    expect(snap.projects[0].counts).toEqual({ documents: 4, chunks: 10, embeddings: 8, pendingEmbeddings: 2 })
    expect(snap.projects[0].index).toEqual({
      finishedAt: '2026-09-23T09:00:00Z',
      mode: 'incremental',
      source: 'cli',
      branch: 'main',
      commit: 'c1',
    })
    expect(snap.projects[0].hooksInstalled).toBe(true)
    expect(snap.projects[0].embeddingProvider).toBe('ollama')
    expect(snap.projects[0].hasStatusFile).toBe(true)
  })

  it('(b) projeto sem status.json cai para readStats e calcula pendingEmbeddings', async () => {
    const snap = await buildSnapshot(
      baseDeps({ readStatus: () => null, readStats: () => ({ documents: 3, chunks: 10, embeddings: 4 }) }),
    )
    expect(snap.projects[0].counts).toEqual({ documents: 3, chunks: 10, embeddings: 4, pendingEmbeddings: 6 })
    expect(snap.projects[0].index).toBeNull()
    expect(snap.projects[0].hasStatusFile).toBe(false)
  })

  it('(b2) readStats indisponível devolve counts null com o motivo', async () => {
    const snap = await buildSnapshot(
      baseDeps({
        readStatus: () => null,
        readStats: () => ({ unavailable: true, reason: 'projeto ainda não foi indexado' }),
      }),
    )
    expect(snap.projects[0].counts).toBeNull()
    expect(snap.projects[0].countsUnavailableReason).toBe('projeto ainda não foi indexado')
  })

  it('(c) pasta ausente: exists false, sem chamar readGit nem readStatus', async () => {
    const readGit = vi.fn(async (): Promise<GitHead | null> => ({ branch: 'main', commit: 'c1' }))
    const readStatus = vi.fn(() => null)
    const snap = await buildSnapshot(baseDeps({ exists: () => false, readGit, readStatus }))
    expect(snap.projects[0].exists).toBe(false)
    expect(snap.projects[0].git).toBeNull()
    expect(snap.projects[0].counts).toBeNull()
    expect(readGit).not.toHaveBeenCalled()
    expect(readStatus).not.toHaveBeenCalled()
  })

  it('(d) readGit lançando isola só aquele projeto', async () => {
    const readGit = vi.fn(async (p: string): Promise<GitHead | null> => {
      if (p === 'C:/p2') throw new Error('git falhou')
      return { branch: 'main', commit: 'c1' }
    })
    const snap = await buildSnapshot(
      baseDeps({
        readRegistry: () => [project({ id: 'p1', path: 'C:/p1' }), project({ id: 'p2', path: 'C:/p2' })],
        readGit,
      }),
    )
    expect(snap.projects[0].git).toEqual({ branch: 'main', commit: 'c1' })
    expect(snap.projects[1].git).toBeNull()
  })

  it('(e) readRegistry lançando devolve o último snapshot bom', async () => {
    const good = await buildSnapshot(baseDeps())
    const bad = await buildSnapshot(
      baseDeps({
        readRegistry: () => {
          throw new Error('registry.json corrompido')
        },
      }),
    )
    expect(bad).toBe(good)
  })

  it('(f) running do status.json vira {source, startedAt}', async () => {
    const snap = await buildSnapshot(
      baseDeps({
        readStatus: () =>
          statusFile({
            running: { pid: 123, op: 'index', source: 'hook:post-commit', started_at: '2026-09-23T09:30:00Z' },
          }),
      }),
    )
    expect(snap.projects[0].running).toEqual({ source: 'hook:post-commit', startedAt: '2026-09-23T09:30:00Z' })
  })

  it('(g) telemetry.lastCallAt é repassado', async () => {
    const snap = await buildSnapshot(
      baseDeps({
        readTelemetry: () => ({ callsByTool: [], totalCalls: 3, tokensDelivered: 100, lastCallAt: '2026-09-23T08:00:00Z' }),
      }),
    )
    expect(snap.projects[0].telemetry.lastCallAt).toBe('2026-09-23T08:00:00Z')
  })

  it('(h) running com pid que não existe mais vira null (índice cancelado ou hook morto)', async () => {
    const asked: number[] = []
    const snap = await buildSnapshot(
      baseDeps({
        readStatus: () =>
          statusFile({
            running: { pid: 4242, op: 'index', source: 'panel', started_at: '2026-09-23T09:30:00Z' },
          }),
        isPidAlive: (pid) => {
          asked.push(pid)
          return false
        },
      }),
    )
    expect(asked).toEqual([4242])
    expect(snap.projects[0].running).toBeNull()
  })

  it('(i) isPidAlive real: o próprio processo está vivo, um pid inexistente não', async () => {
    const { isPidAlive } = await import('../snapshot')
    expect(isPidAlive(process.pid)).toBe(true)
    expect(isPidAlive(2 ** 22 + 12345)).toBe(false)
  })

  it('(j) isPidAlive: EPERM (processo de outro usuário) conta como vivo; ESRCH como morto', async () => {
    const { isPidAlive } = await import('../snapshot')
    const eperm = Object.assign(new Error('eperm'), { code: 'EPERM' })
    const esrch = Object.assign(new Error('esrch'), { code: 'ESRCH' })
    expect(isPidAlive(10, () => { throw eperm })).toBe(true)
    expect(isPidAlive(10, () => { throw esrch })).toBe(false)
    expect(isPidAlive(10, () => true)).toBe(true)
  })
})

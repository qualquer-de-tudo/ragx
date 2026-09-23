import { describe, expect, it } from 'vitest'
import { deriveProjectState } from '../state'
import type { ProjectSnapshot } from '../types/ragx-bridge'

export function snap(over: Partial<ProjectSnapshot> = {}): ProjectSnapshot {
  return {
    id: 'p1', name: 'p1', path: 'C:/p1', exists: true,
    embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama', visibility: 'workspace',
    counts: { documents: 3, chunks: 10, embeddings: 10, pendingEmbeddings: 0 },
    countsUnavailableReason: null,
    index: { finishedAt: '2026-09-23T10:00:00Z', mode: 'incremental', source: 'cli', branch: 'main', commit: 'c1' },
    git: { branch: 'main', commit: 'c1' },
    hooksInstalled: true, running: null, pending: false, lastError: null, hasStatusFile: true,
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null },
    ...over,
  }
}

const none = new Set<string>()

describe('deriveProjectState', () => {
  it('ok quando tudo bate', () => expect(deriveProjectState(snap(), none)).toBe('ok'))
  it('pasta ausente vence tudo', () =>
    expect(deriveProjectState(snap({ exists: false, running: { source: 'cli', startedAt: 'x' } }), none)).toBe('missing'))
  it('indexando pelo status.json ou pela fila', () => {
    expect(deriveProjectState(snap({ running: { source: 'hook:post-commit', startedAt: 'x' } }), none)).toBe('indexing')
    expect(deriveProjectState(snap(), new Set(['p1']))).toBe('indexing')
  })
  it('erro quando não há contagem ou há last_error', () => {
    expect(deriveProjectState(snap({ counts: null }), none)).toBe('error')
    expect(deriveProjectState(snap({ lastError: 'embedder fora' }), none)).toBe('error')
  })
  it('embeddings faltando antes de defasado', () =>
    expect(deriveProjectState(snap({
      counts: { documents: 3, chunks: 10, embeddings: 4, pendingEmbeddings: 6 },
      git: { branch: 'feat', commit: 'c2' },
    }), none)).toBe('embeddings'))
  it('defasado quando nunca indexou com o RAGX novo', () =>
    expect(deriveProjectState(snap({ index: null }), none)).toBe('stale'))
  it('defasado quando o commit ou a branch mudou', () => {
    expect(deriveProjectState(snap({ git: { branch: 'main', commit: 'c2' } }), none)).toBe('stale')
    expect(deriveProjectState(snap({ git: { branch: 'feat/x', commit: 'c1' } }), none)).toBe('stale')
  })
  it('HEAD destacado no mesmo commit não é defasado', () =>
    expect(deriveProjectState(snap({ git: { branch: null, commit: 'c1' } }), none)).toBe('ok'))
  it('sem hooks só quando o resto está em dia', () =>
    expect(deriveProjectState(snap({ hooksInstalled: false }), none)).toBe('no-hooks'))
  it('hooks desconhecidos (fora de repo) não viram "sem hooks"', () =>
    expect(deriveProjectState(snap({ hooksInstalled: null, git: null }), none)).toBe('ok'))
})

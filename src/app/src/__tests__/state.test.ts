import { describe, expect, it } from 'vitest'
import { activeConnectionJob, activeOllamaSwitch, busyProjectIds, deriveProjectState } from '../state'
import { job, snap } from '../test/snap'

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

describe('busyProjectIds', () => {
  it('só tarefas de indexação na fila ou rodando contam', () => {
    for (const kind of ['add-project', 'update', 'embed', 'reindex-full'] as const) {
      expect(busyProjectIds([job({ kind, state: 'running' })])).toEqual(new Set(['p1']))
      expect(busyProjectIds([job({ kind, state: 'queued' })])).toEqual(new Set(['p1']))
    }
    expect(busyProjectIds([job({ kind: 'embed', state: 'done' })])).toEqual(new Set())
  })

  it('sync, grafo, dicionário e hooks não deixam o projeto "Indexando…"', () => {
    const jobs = (['sync', 'graph', 'dictionary', 'hooks-install', 'hooks-uninstall', 'remove-from-hub'] as const).map(
      (kind, i) => job({ id: `j${i}`, kind, state: 'running' }),
    )
    const busy = busyProjectIds(jobs)
    expect(busy).toEqual(new Set())
    expect(deriveProjectState(snap(), busy)).toBe('ok')
  })

  it('um embed rodando deixa o projeto "Indexando…"', () =>
    expect(deriveProjectState(snap(), busyProjectIds([job({ kind: 'embed', state: 'running' })]))).toBe('indexing'))
})

describe('activeConnectionJob', () => {
  it('reconhece trocar, parar e iniciar o Ollama pelo tipo', () => {
    for (const kind of ['ollama-use-native', 'ollama-use-docker', 'ollama-stop', 'ollama-start'] as const) {
      const running = job({ id: kind, kind, projectId: null })
      expect(activeConnectionJob([running], { kind, label: 'x' })).toBe(running)
      expect(activeConnectionJob([{ ...running, state: 'done' }], { kind, label: 'x' })).toBeNull()
    }
    // Outro tipo não ocupa o botão.
    expect(
      activeConnectionJob([job({ kind: 'ollama-use-docker', projectId: null })], { kind: 'ollama-use-native', label: 'x' }),
    ).toBeNull()
  })

  it('o pull só conta se for do mesmo modelo; a rodando vence a da fila', () => {
    const queued = job({ id: 'q', kind: 'ollama-pull', model: 'bge-m3', projectId: null, state: 'queued' })
    const running = job({ id: 'r', kind: 'ollama-pull', model: 'bge-m3', projectId: null, state: 'running' })
    const pull = { kind: 'ollama-pull' as const, label: 'Baixar bge-m3', model: 'bge-m3' }
    expect(activeConnectionJob([queued, running], pull)).toBe(running)
    expect(activeConnectionJob([queued], { ...pull, model: 'nomic-embed-text' })).toBeNull()
  })

  it('medir velocidade nunca é tarefa da fila', () =>
    expect(activeConnectionJob([job({ kind: 'ollama-stop', projectId: null })], { kind: 'ollama-benchmark', label: 'x' })).toBeNull())
})

describe('activeOllamaSwitch', () => {
  it('troca para local ou Docker, na fila ou rodando', () => {
    const native = job({ id: 'n', kind: 'ollama-use-native', label: 'Usar o Ollama local', projectId: null, state: 'queued' })
    const docker = job({ id: 'd', kind: 'ollama-use-docker', label: 'Usar o Ollama no Docker', projectId: null })
    expect(activeOllamaSwitch([native])).toBe(native)
    expect(activeOllamaSwitch([native, docker])).toBe(docker)
    expect(activeOllamaSwitch([{ ...docker, state: 'failed' }])).toBeNull()
    expect(activeOllamaSwitch([job({ kind: 'ollama-stop', projectId: null })])).toBeNull()
  })
})

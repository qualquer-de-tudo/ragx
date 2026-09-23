import { describe, expect, it } from 'vitest'
import { resolveJob, JobRejected, MODEL_PATTERN, type CatalogContext } from '../catalog'
import type { JobRequest } from '../../../src/types/ragx-bridge'

const PROJECT = { id: 'p1', name: 'Juriflux', path: 'C:/proj/juriflux' }
const FEDERATED = { id: 'so-federacao', name: 'Federado', path: null }

const FOLDERS: Record<string, string> = { 'tok-1': 'C:/pastas/NovoProjeto', 'tok-2': 'C:/pastas/OutroProjeto' }

function ctx(over: Partial<CatalogContext> = {}): CatalogContext {
  return {
    projectById: (id) => [PROJECT, FEDERATED].find((p) => p.id === id),
    folderByToken: (token) => FOLDERS[token],
    ...over,
  }
}

describe('resolveJob - tabela do catálogo', () => {
  it('add-project: init, index --progress, sem installHooks', () => {
    const job = resolveJob({ kind: 'add-project', folderToken: 'tok-1' }, ctx())
    expect(job.kind).toBe('add-project')
    expect(job.label).toBe('Adicionar NovoProjeto')
    expect(job.projectId).toBeNull()
    expect(job.steps).toEqual([
      { cmd: 'ragx', args: ['init', 'C:/pastas/NovoProjeto'], cwd: null, progress: false },
      {
        cmd: 'ragx',
        args: ['index', 'C:/pastas/NovoProjeto', '--progress', '--source', 'panel'],
        cwd: null,
        progress: true,
      },
    ])
  })

  it('add-project: com installHooks true adiciona o terceiro passo', () => {
    const job = resolveJob({ kind: 'add-project', folderToken: 'tok-1', installHooks: true }, ctx())
    expect(job.steps).toHaveLength(3)
    expect(job.steps[2]).toEqual({
      cmd: 'ragx',
      args: ['hooks', 'install', 'C:/pastas/NovoProjeto'],
      cwd: null,
      progress: false,
    })
  })

  it('update', () => {
    const job = resolveJob({ kind: 'update', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Atualizar Juriflux')
    expect(job.projectId).toBe('p1')
    expect(job.steps).toEqual([
      { cmd: 'ragx', args: ['index', 'C:/proj/juriflux', '--progress', '--source', 'panel'], cwd: null, progress: true },
    ])
  })

  it('embed', () => {
    const job = resolveJob({ kind: 'embed', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Gerar embeddings em Juriflux')
    expect(job.steps).toEqual([
      {
        cmd: 'ragx',
        args: ['index', 'C:/proj/juriflux', '--embed-only', '--progress', '--source', 'panel'],
        cwd: null,
        progress: true,
      },
    ])
  })

  it('reindex-full', () => {
    const job = resolveJob({ kind: 'reindex-full', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Reindexar Juriflux do zero')
    expect(job.steps).toEqual([
      {
        cmd: 'ragx',
        args: ['index', 'C:/proj/juriflux', '--full', '--progress', '--source', 'panel'],
        cwd: null,
        progress: true,
      },
    ])
  })

  it('sync', () => {
    const job = resolveJob({ kind: 'sync', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Sincronizar knowledge de Juriflux')
    expect(job.steps).toEqual([{ cmd: 'ragx', args: ['sync'], cwd: 'C:/proj/juriflux', progress: false }])
  })

  it('graph', () => {
    const job = resolveJob({ kind: 'graph', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Reconstruir grafo de Juriflux')
    expect(job.steps).toEqual([{ cmd: 'ragx', args: ['graph', 'rebuild'], cwd: 'C:/proj/juriflux', progress: false }])
  })

  it('dictionary', () => {
    const job = resolveJob({ kind: 'dictionary', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Gerar dicionário de Juriflux')
    expect(job.steps).toEqual([
      { cmd: 'ragx', args: ['dictionary', 'generate'], cwd: 'C:/proj/juriflux', progress: false },
    ])
  })

  it('hooks-install', () => {
    const job = resolveJob({ kind: 'hooks-install', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Instalar hooks em Juriflux')
    expect(job.steps).toEqual([
      { cmd: 'ragx', args: ['hooks', 'install', 'C:/proj/juriflux'], cwd: null, progress: false },
    ])
  })

  it('hooks-uninstall', () => {
    const job = resolveJob({ kind: 'hooks-uninstall', projectId: 'p1' }, ctx())
    expect(job.label).toBe('Remover hooks de Juriflux')
    expect(job.steps).toEqual([
      { cmd: 'ragx', args: ['hooks', 'uninstall', 'C:/proj/juriflux'], cwd: null, progress: false },
    ])
  })

  it('remove-from-hub: usa o nome, nao o caminho, e funciona sem path (so federacao)', () => {
    const job = resolveJob({ kind: 'remove-from-hub', projectId: 'so-federacao' }, ctx())
    expect(job.label).toBe('Remover Federado do hub')
    expect(job.steps).toEqual([{ cmd: 'ragx', args: ['project', 'unregister', 'Federado'], cwd: null, progress: false }])
  })

  it('mcp-register: sem projeto', () => {
    const job = resolveJob({ kind: 'mcp-register' }, ctx())
    expect(job.label).toBe('Registrar o RAGX no Claude Code')
    expect(job.projectId).toBeNull()
    expect(job.steps).toEqual([
      { cmd: 'ragx', args: ['mcp', 'install', '--client', 'claude-code'], cwd: null, progress: false },
    ])
  })

  it('ollama-start', () => {
    const job = resolveJob({ kind: 'ollama-start' }, ctx())
    expect(job.label).toBe('Iniciar o container ollama')
    expect(job.steps).toEqual([{ cmd: 'docker', args: ['start', 'ollama'], cwd: null, progress: false }])
  })

  it('ollama-pull', () => {
    const job = resolveJob({ kind: 'ollama-pull', model: 'nomic-embed-text' }, ctx())
    expect(job.label).toBe('Baixar o modelo nomic-embed-text')
    expect(job.steps).toEqual([
      { cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'nomic-embed-text'], cwd: null, progress: false },
    ])
  })
})

describe('resolveJob - recusas', () => {
  function expectRejected(req: JobRequest, c: CatalogContext = ctx()): void {
    expect(() => resolveJob(req, c)).toThrow(JobRejected)
  }

  it('projectId de tarefa de projeto desconhecido (inclusive tentativa de path traversal)', () => {
    expectRejected({ kind: 'update', projectId: '../../etc' })
  })

  it('tarefa de projeto sem projectId', () => {
    expectRejected({ kind: 'update' } as JobRequest)
  })

  it('kind fora do catalogo', () => {
    expectRejected({ kind: 'nuke' } as unknown as JobRequest)
  })

  it('ollama-pull com model contendo shell injection', () => {
    expectRejected({ kind: 'ollama-pull', model: 'x; rm -rf /' })
  })

  it('ollama-pull com model parecendo uma flag', () => {
    expectRejected({ kind: 'ollama-pull', model: '--help' })
  })

  it('add-project com token de pasta desconhecido', () => {
    expectRejected({ kind: 'add-project', folderToken: 'nao-existe' })
  })

  it('embed em projeto so de federacao (path null)', () => {
    expectRejected({ kind: 'embed', projectId: 'so-federacao' })
  })

  it('campo extra com tipo errado (installHooks nao booleano)', () => {
    expectRejected({ kind: 'add-project', folderToken: 'tok-1', installHooks: 'sim' } as unknown as JobRequest)
  })
})

describe('MODEL_PATTERN', () => {
  it('aceita nomes simples e com namespace/tag', () => {
    expect(MODEL_PATTERN.test('nomic-embed-text')).toBe(true)
    expect(MODEL_PATTERN.test('library/nomic-embed-text:latest')).toBe(true)
  })

  it('rejeita injecao de shell e flags', () => {
    expect(MODEL_PATTERN.test('x; rm -rf /')).toBe(false)
    expect(MODEL_PATTERN.test('--help')).toBe(false)
  })
})

// Fix round 1: `dedupeKey` precisa distinguir pedidos que `kind`+`projectId`
// sozinhos não distinguem - `ollama-pull` e `add-project` sempre têm
// `projectId: null`, então sem isso dois modelos ou duas pastas diferentes
// colidiriam no dedupe de `JobQueue.enqueue`.
describe('resolveJob - dedupeKey', () => {
  it('ollama-pull: modelos diferentes geram dedupeKey diferente', () => {
    const a = resolveJob({ kind: 'ollama-pull', model: 'nomic-embed-text' }, ctx())
    const b = resolveJob({ kind: 'ollama-pull', model: 'mxbai-embed-large' }, ctx())
    expect(a.dedupeKey).not.toBe(b.dedupeKey)
  })

  it('ollama-pull: o mesmo modelo gera a mesma dedupeKey', () => {
    const a = resolveJob({ kind: 'ollama-pull', model: 'nomic-embed-text' }, ctx())
    const b = resolveJob({ kind: 'ollama-pull', model: 'nomic-embed-text' }, ctx())
    expect(a.dedupeKey).toBe(b.dedupeKey)
  })

  it('add-project: tokens de pasta diferentes geram dedupeKey diferente', () => {
    const a = resolveJob({ kind: 'add-project', folderToken: 'tok-1' }, ctx())
    const b = resolveJob({ kind: 'add-project', folderToken: 'tok-2' }, ctx())
    expect(a.dedupeKey).not.toBe(b.dedupeKey)
  })

  it('mesmo kind+projeto ainda gera a mesma dedupeKey (regressão)', () => {
    const a = resolveJob({ kind: 'update', projectId: 'p1' }, ctx())
    const b = resolveJob({ kind: 'update', projectId: 'p1' }, ctx())
    expect(a.dedupeKey).toBe(b.dedupeKey)
  })
})

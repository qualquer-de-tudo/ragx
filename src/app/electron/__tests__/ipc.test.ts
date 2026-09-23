import { describe, expect, it, vi } from 'vitest'
import { createHandlers, type HandlerDeps, type QueueLike } from '../ipc'
import { FolderTokens } from '../projects/tokens'
import type { ResolvedJob } from '../jobs/catalog'
import type { JobView, ProjectSnapshot, Snapshot } from '../../src/types/ragx-bridge'

const PROJECT_A: ProjectSnapshot = {
  id: 'a',
  name: 'Projeto A',
  path: 'C:/proj/a',
  exists: true,
  embeddingModel: null,
  embeddingProvider: null,
  visibility: 'workspace',
  counts: null,
  countsUnavailableReason: null,
  index: null,
  git: null,
  hooksInstalled: null,
  running: null,
  pending: false,
  lastError: null,
  hasStatusFile: false,
  telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null },
}

const PROJECT_FEDERADO: ProjectSnapshot = { ...PROJECT_A, id: 'federado', name: 'Federado', path: null }

const SNAPSHOT: Snapshot = { projects: [PROJECT_A, PROJECT_FEDERADO], generatedAt: '2026-09-23T10:00:00Z' }

function fakeQueue(): QueueLike & { enqueued: ResolvedJob[] } {
  const enqueued: ResolvedJob[] = []
  return {
    enqueued,
    enqueue: (job: ResolvedJob): JobView => {
      enqueued.push(job)
      return {
        id: `job-${String(enqueued.length)}`,
        kind: job.kind,
        label: job.label,
        projectId: job.projectId,
        state: 'queued',
        step: 1,
        steps: job.steps.length,
        phase: null,
        done: null,
        total: null,
        etaSeconds: null,
        ratePerSecond: null,
        note: null,
        error: null,
        logTail: [],
        queuedAt: '2026-09-23T10:00:00Z',
        startedAt: null,
        finishedAt: null,
      }
    },
    cancel: vi.fn(() => true),
    list: vi.fn(() => []),
  }
}

function makeDeps(over: Partial<HandlerDeps> = {}): HandlerDeps {
  return {
    buildSnapshot: vi.fn(async () => SNAPSHOT),
    getCachedSnapshot: () => SNAPSHOT,
    runRagxCommand: vi.fn(async () => ({})),
    checkAll: vi.fn(async () => []),
    resetRagxCache: vi.fn(),
    queue: fakeQueue(),
    folderTokens: new FolderTokens(),
    discoverProjects: vi.fn(() => []),
    showOpenDialog: vi.fn(async () => null),
    readSettings: vi.fn(() => ({ onboardingDone: false })),
    writeSettings: vi.fn(),
    ...over,
  }
}

describe('createHandlers - runTrial/getProjectStatus/runSecurityScan validam projectId contra o snapshot', () => {
  it('runTrial roda "ragx trial --json" com o cwd do projeto encontrado no snapshot', async () => {
    const runRagxCommand = vi.fn(async () => ({ totals: { baseline_tokens: 1, ragx_tokens: 1, saved_ratio: 0, source_coverage: 1 } }))
    const handlers = createHandlers(makeDeps({ runRagxCommand }))

    await handlers.runTrial('a')

    expect(runRagxCommand).toHaveBeenCalledWith('C:/proj/a', ['trial', '--json'])
  })

  it('getProjectStatus roda "ragx status --json" com o cwd do projeto', async () => {
    const runRagxCommand = vi.fn(async () => ({ ok: true }))
    const handlers = createHandlers(makeDeps({ runRagxCommand }))

    await handlers.getProjectStatus('a')

    expect(runRagxCommand).toHaveBeenCalledWith('C:/proj/a', ['status', '--json'])
  })

  it('runSecurityScan roda "ragx security scan . --json" com o cwd do projeto', async () => {
    const runRagxCommand = vi.fn(async () => ({ root: 'C:/proj/a', scanned: 0, blocked: [], redacted: [], skipped: 0, ruleset: { version: 'x', rules: 0, disabled: [] }, policy: 'strict' }))
    const handlers = createHandlers(makeDeps({ runRagxCommand }))

    await handlers.runSecurityScan('a')

    expect(runRagxCommand).toHaveBeenCalledWith('C:/proj/a', ['security', 'scan', '.', '--json'])
  })

  it('runTrial com um projectId que nao existe no snapshot (mesmo parecendo um caminho) e recusado antes de qualquer processo', async () => {
    const runRagxCommand = vi.fn(async () => ({}))
    const handlers = createHandlers(makeDeps({ runRagxCommand }))

    await expect(handlers.runTrial('C:/Windows')).rejects.toThrow(/pedido recusado/)
    expect(runRagxCommand).not.toHaveBeenCalled()
  })

  it('runTrial com projectId de tipo errado e recusado', async () => {
    const runRagxCommand = vi.fn(async () => ({}))
    const handlers = createHandlers(makeDeps({ runRagxCommand }))

    await expect(handlers.runTrial(42)).rejects.toThrow(/pedido recusado/)
    expect(runRagxCommand).not.toHaveBeenCalled()
  })

  it('runTrial num projeto so de federacao (sem path local) e recusado', async () => {
    const runRagxCommand = vi.fn(async () => ({}))
    const handlers = createHandlers(makeDeps({ runRagxCommand }))

    await expect(handlers.runTrial('federado')).rejects.toThrow(/pedido recusado/)
    expect(runRagxCommand).not.toHaveBeenCalled()
  })
})

describe('createHandlers - enqueueJob valida forma, chama resolveJob e enfileira', () => {
  it('kind=update com projectId conhecido chega na fila com os passos do catalogo', () => {
    const queue = fakeQueue()
    const handlers = createHandlers(makeDeps({ queue }))

    const view = handlers.enqueueJob({ kind: 'update', projectId: 'a' })

    expect(queue.enqueued).toHaveLength(1)
    expect(queue.enqueued[0]).toMatchObject({
      kind: 'update',
      projectId: 'a',
      steps: [{ cmd: 'ragx', args: ['index', 'C:/proj/a', '--progress', '--source', 'panel'], cwd: null, progress: true }],
    })
    expect(view.id).toBe('job-1')
  })

  it('recusa um pedido com chave extra fora do catalogo (ex.: path livre)', () => {
    const queue = fakeQueue()
    const handlers = createHandlers(makeDeps({ queue }))

    expect(() => handlers.enqueueJob({ kind: 'update', projectId: 'a', path: 'C:/x' })).toThrow(/pedido recusado/)
    expect(queue.enqueued).toHaveLength(0)
  })

  it('recusa embed num projeto so de federacao (sem path)', () => {
    const queue = fakeQueue()
    const handlers = createHandlers(makeDeps({ queue }))

    expect(() => handlers.enqueueJob({ kind: 'embed', projectId: 'federado' })).toThrow(/pedido recusado/)
    expect(queue.enqueued).toHaveLength(0)
  })

  it('recusa ollama-pull com model contendo injecao de shell, antes de qualquer processo', () => {
    const queue = fakeQueue()
    const handlers = createHandlers(makeDeps({ queue }))

    expect(() => handlers.enqueueJob({ kind: 'ollama-pull', model: 'x; rm -rf /' })).toThrow(/pedido recusado/)
    expect(queue.enqueued).toHaveLength(0)
  })

  it('recusa um pedido que nao e objeto', () => {
    const handlers = createHandlers(makeDeps())
    expect(() => handlers.enqueueJob('update')).toThrow(/pedido recusado/)
    expect(() => handlers.enqueueJob(null)).toThrow(/pedido recusado/)
  })
})

describe('createHandlers - discover so aceita token conhecido e devolve tokens novos', () => {
  it('recusa um token desconhecido', () => {
    const handlers = createHandlers(makeDeps())
    expect(() => handlers.discover('token-invalido')).toThrow(/pedido recusado/)
  })

  it('recusa token de tipo errado', () => {
    const handlers = createHandlers(makeDeps())
    expect(() => handlers.discover(42)).toThrow(/pedido recusado/)
  })

  it('devolve itens com token proprio (diferente do token de entrada), usavel depois em add-project', () => {
    const queue = fakeQueue()
    const discoverProjects = vi.fn(() => [{ path: 'C:/pastas/Novo', name: 'Novo', alreadyRegistered: false }])
    const deps = makeDeps({ discoverProjects, queue })
    const handlers = createHandlers(deps)

    const rootToken = deps.folderTokens.issue('C:/pastas')
    const items = handlers.discover(rootToken)

    expect(discoverProjects).toHaveBeenCalledWith('C:/pastas', new Set(['C:/proj/a']))
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ path: 'C:/pastas/Novo', name: 'Novo', alreadyRegistered: false })
    expect(items[0].token).not.toBe(rootToken)
    expect(deps.folderTokens.get(items[0].token)).toBe('C:/pastas/Novo')

    // O token devolvido por discover funciona direto num add-project (3 passos com installHooks).
    handlers.enqueueJob({ kind: 'add-project', folderToken: items[0].token, installHooks: true })
    expect(queue.enqueued[0].steps).toHaveLength(3)
    expect(queue.enqueued[0].steps[0]).toEqual({ cmd: 'ragx', args: ['init', 'C:/pastas/Novo'], cwd: null, progress: false })
  })
})

describe('createHandlers - cancelJob/listJobs', () => {
  it('cancelJob recusa um jobId de tipo errado', () => {
    const handlers = createHandlers(makeDeps())
    expect(() => handlers.cancelJob(42)).toThrow(/pedido recusado/)
  })

  it('cancelJob repassa um jobId valido para a fila', () => {
    const queue = fakeQueue()
    const handlers = createHandlers(makeDeps({ queue }))
    expect(handlers.cancelJob('job-1')).toBe(true)
    expect(queue.cancel).toHaveBeenCalledWith('job-1')
  })

  it('listJobs repassa a lista da fila', () => {
    const queue = fakeQueue()
    const handlers = createHandlers(makeDeps({ queue }))
    handlers.listJobs()
    expect(queue.list).toHaveBeenCalledOnce()
  })
})

describe('createHandlers - getConnections', () => {
  it('reseta o cache do ragx e roda as checagens contra o snapshot em cache', async () => {
    const resetRagxCache = vi.fn()
    const checkAll = vi.fn(async () => [])
    const buildSnapshot = vi.fn(async () => SNAPSHOT)
    const handlers = createHandlers(makeDeps({ resetRagxCache, checkAll, buildSnapshot, getCachedSnapshot: () => SNAPSHOT }))

    await handlers.getConnections()

    expect(resetRagxCache).toHaveBeenCalledOnce()
    expect(checkAll).toHaveBeenCalledWith(SNAPSHOT)
    expect(buildSnapshot).not.toHaveBeenCalled()
  })

  it('constroi um snapshot quando ainda nao ha nenhum em cache', async () => {
    const checkAll = vi.fn(async () => [])
    const buildSnapshot = vi.fn(async () => SNAPSHOT)
    const handlers = createHandlers(makeDeps({ checkAll, buildSnapshot, getCachedSnapshot: () => null }))

    await handlers.getConnections()

    expect(buildSnapshot).toHaveBeenCalledOnce()
    expect(checkAll).toHaveBeenCalledWith(SNAPSHOT)
  })
})

describe('createHandlers - pickFolder', () => {
  it('devolve null quando o dialogo e cancelado', async () => {
    const handlers = createHandlers(makeDeps({ showOpenDialog: vi.fn(async () => null) }))
    expect(await handlers.pickFolder()).toBeNull()
  })

  it('devolve um token novo e o caminho escolhido quando o usuario confirma', async () => {
    const deps = makeDeps({ showOpenDialog: vi.fn(async () => 'C:/pastas/Escolhida') })
    const handlers = createHandlers(deps)

    const result = await handlers.pickFolder()

    expect(result).not.toBeNull()
    expect(result?.path).toBe('C:/pastas/Escolhida')
    expect(deps.folderTokens.get(result!.token)).toBe('C:/pastas/Escolhida')
  })
})

describe('createHandlers - getSettings/setOnboardingDone', () => {
  it('getSettings repassa o que readSettings devolve', () => {
    const handlers = createHandlers(makeDeps({ readSettings: () => ({ onboardingDone: true }) }))
    expect(handlers.getSettings()).toEqual({ onboardingDone: true })
  })

  it('setOnboardingDone recusa um valor nao booleano', () => {
    const writeSettings = vi.fn()
    const handlers = createHandlers(makeDeps({ writeSettings }))
    expect(() => handlers.setOnboardingDone('sim')).toThrow(/pedido recusado/)
    expect(writeSettings).not.toHaveBeenCalled()
  })

  it('setOnboardingDone grava um valor booleano valido', () => {
    const writeSettings = vi.fn()
    const handlers = createHandlers(makeDeps({ writeSettings }))
    handlers.setOnboardingDone(true)
    expect(writeSettings).toHaveBeenCalledWith({ onboardingDone: true })
  })
})

describe('createHandlers - getSnapshot', () => {
  it('delega em buildSnapshot', async () => {
    const buildSnapshot = vi.fn(async () => SNAPSHOT)
    const handlers = createHandlers(makeDeps({ buildSnapshot }))
    expect(await handlers.getSnapshot()).toBe(SNAPSHOT)
    expect(buildSnapshot).toHaveBeenCalledOnce()
  })
})

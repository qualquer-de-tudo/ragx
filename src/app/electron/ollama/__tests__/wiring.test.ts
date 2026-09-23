import { describe, expect, it, vi } from 'vitest'
import {
  conditionFrom,
  createOllamaEnvCache,
  distinctRequiredModels,
  ollamaFollowUps,
  waitForApi,
} from '../wiring'
import type { JobView, OllamaEnvironment, ProjectSnapshot, Snapshot } from '../../../src/types/ragx-bridge'

function env(over: Partial<OllamaEnvironment> = {}): OllamaEnvironment {
  return {
    platform: 'win32',
    gpu: { vendor: 'none', name: null },
    docker: { installed: true, running: true },
    container: { exists: false, running: false },
    native: { installed: false, path: null, running: false },
    canInstallNative: true,
    apiUp: false,
    models: [],
    mode: 'none',
    recommendation: { mode: 'docker', reason: 'x' },
    ...over,
  }
}

describe('conditionFrom', () => {
  it('mapeia cada condição para o campo certo do ambiente', () => {
    const cases: Array<[Parameters<typeof conditionFrom>[1], Partial<OllamaEnvironment>, boolean]> = [
      ['container-running', { container: { exists: true, running: true } }, true],
      ['container-running', { container: { exists: true, running: false } }, false],
      ['container-exists', { container: { exists: true, running: false } }, true],
      ['container-exists', { container: { exists: false, running: false } }, false],
      ['container-missing', { container: { exists: false, running: false } }, true],
      ['container-missing', { container: { exists: true, running: false } }, false],
      ['native-running', { native: { installed: true, path: 'x', running: true } }, true],
      ['native-running', { native: { installed: true, path: 'x', running: false } }, false],
      ['native-missing', { native: { installed: false, path: null, running: false } }, true],
      ['native-missing', { native: { installed: true, path: 'x', running: false } }, false],
      ['native-not-running', { native: { installed: true, path: 'x', running: false } }, true],
      ['native-not-running', { native: { installed: true, path: 'x', running: true } }, false],
    ]
    for (const [cond, over, expected] of cases) {
      expect(conditionFrom(env(over), cond), `${cond} ${JSON.stringify(over)}`).toBe(expected)
    }
  })

  it('condição desconhecida lança (a fila transforma em falha legível), nunca roda o passo por engano', () => {
    expect(() => conditionFrom(env(), 'qualquer' as never)).toThrow()
  })
})

const BASE: ProjectSnapshot = {
  id: 'a',
  name: 'A',
  path: 'C:/a',
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

function snap(projects: Array<Partial<ProjectSnapshot>>): Snapshot {
  return { projects: projects.map((p, i) => ({ ...BASE, id: `p${i}`, ...p })), generatedAt: '2026-09-23T10:00:00Z' }
}

describe('distinctRequiredModels', () => {
  it('sem snapshot: nenhum modelo', () => {
    expect(distinctRequiredModels(null)).toEqual([])
  })

  it('provider ollama, ou provider nulo com nome sem barra; sem repetição e sem vazio', () => {
    const s = snap([
      { embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' },
      { embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' },
      { embeddingModel: 'mxbai-embed-large', embeddingProvider: null },
      { embeddingModel: 'sentence-transformers/all-MiniLM-L6-v2', embeddingProvider: null },
      { embeddingModel: 'text-embedding-3-small', embeddingProvider: 'openai' },
      { embeddingModel: '', embeddingProvider: 'ollama' },
      { embeddingModel: '   ', embeddingProvider: 'ollama' },
      { embeddingModel: null, embeddingProvider: 'ollama' },
    ])
    expect(distinctRequiredModels(s)).toEqual(['nomic-embed-text', 'mxbai-embed-large'])
  })
})

describe('waitForApi', () => {
  function clock() {
    let t = 0
    return {
      now: () => t,
      sleep: vi.fn(async (ms: number) => {
        t += ms
      }),
    }
  }

  it('responde true assim que a API atende', async () => {
    const c = clock()
    const poll = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    expect(await waitForApi(60_000, { poll, ...c })).toBe(true)
    expect(poll).toHaveBeenCalledTimes(3)
    expect(c.sleep).toHaveBeenCalledTimes(2)
    expect(c.sleep).toHaveBeenCalledWith(1000)
  })

  it('respeita o prazo sozinha: false no fim, sem passar do prazo', async () => {
    const c = clock()
    const poll = vi.fn(async () => false)
    expect(await waitForApi(3_500, { poll, ...c })).toBe(false)
    expect(c.now()).toBeLessThanOrEqual(3_500)
    // Sondagens em 0, 1000, 2000 e 3000; cada uma com no máximo o que falta (e nunca 0, que no Node desliga o timeout).
    expect((poll.mock.calls as unknown as Array<[number]>).map(([t]) => t)).toEqual([3_000, 2_500, 1_500, 500])
  })

  it('a sondagem nunca espera além do que falta para o prazo', async () => {
    const c = clock()
    const poll = vi.fn(async () => false)
    await waitForApi(1_500, { poll, ...c })
    const timeouts = (poll.mock.calls as unknown as Array<[number]>).map(([t]) => t)
    expect(timeouts[0]).toBe(1_500)
    expect(timeouts[timeouts.length - 1]).toBeLessThanOrEqual(500)
  })

  it('sondagem que lança conta como "ainda não" e nunca rejeita', async () => {
    const c = clock()
    const poll = vi.fn().mockRejectedValueOnce(new Error('ECONNREFUSED')).mockResolvedValueOnce(true)
    expect(await waitForApi(10_000, { poll, ...c })).toBe(true)
  })

  it('prazo zero, negativo, NaN ou infinito: false na hora, sem sondar nem esperar', async () => {
    for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      const c = clock()
      const poll = vi.fn(async () => true)
      expect(await waitForApi(bad, { poll, ...c }), String(bad)).toBe(false)
      expect(poll).not.toHaveBeenCalled()
      expect(c.sleep).not.toHaveBeenCalled()
    }
  })
})

describe('createOllamaEnvCache', () => {
  function deferred<T>() {
    let resolve: (v: T) => void = () => {}
    const promise = new Promise<T>((r) => (resolve = r))
    return { promise, resolve }
  }

  it('null antes da primeira detecção; guarda a última', async () => {
    const cache = createOllamaEnvCache(async () => env({ mode: 'docker' }))
    expect(cache.get()).toBeNull()
    await cache.fresh()
    expect(cache.get()?.mode).toBe('docker')
  })

  it('shared junta chamadas simultâneas numa detecção só', async () => {
    const d = deferred<OllamaEnvironment>()
    const detect = vi.fn(() => d.promise)
    const cache = createOllamaEnvCache(detect)
    const a = cache.shared()
    const b = cache.shared()
    d.resolve(env())
    expect(await a).toBe(await b)
    expect(detect).toHaveBeenCalledTimes(1)
  })

  it('fresh sempre detecta de novo, mesmo com outra em andamento', async () => {
    const first = deferred<OllamaEnvironment>()
    const detect = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce(env({ mode: 'native' }))
    const cache = createOllamaEnvCache(detect)
    void cache.shared()
    const fresh = await cache.fresh()
    expect(fresh.mode).toBe('native')
    expect(detect).toHaveBeenCalledTimes(2)
    // A detecção antiga que termina depois não sobrescreve a mais nova.
    first.resolve(env({ mode: 'docker' }))
    await first.promise
    await Promise.resolve()
    expect(cache.get()?.mode).toBe('native')
  })

  it('shared chamado enquanto uma fresh roda recebe a fresh', async () => {
    const d = deferred<OllamaEnvironment>()
    const detect = vi.fn(() => d.promise)
    const cache = createOllamaEnvCache(detect)
    const f = cache.fresh()
    const s = cache.shared()
    d.resolve(env())
    expect(await s).toBe(await f)
    expect(detect).toHaveBeenCalledTimes(1)
  })

  it('invalidate: detecção A em andamento, tarefa termina, o próximo shared começa B e A atrasada não sobrescreve B', async () => {
    const a = deferred<OllamaEnvironment>()
    const b = deferred<OllamaEnvironment>()
    const detect = vi.fn().mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const cache = createOllamaEnvCache(detect)

    const antes = cache.shared() // A: polling de 30 s, começou antes da tarefa terminar
    await Promise.resolve()
    cache.invalidate() // a tarefa ollama-* terminou

    const depois = cache.shared() // pedido do renderer depois do fim da tarefa
    await Promise.resolve()
    expect(detect).toHaveBeenCalledTimes(2)
    expect(cache.shared()).toBe(depois) // quem chega agora junta-se a B, não a A

    b.resolve(env({ mode: 'docker' }))
    expect((await depois).mode).toBe('docker')
    a.resolve(env({ mode: 'native' }))
    expect((await antes).mode).toBe('native')
    expect(cache.get()?.mode).toBe('docker')
  })

  it('invalidate sem nada em andamento não faz nada de estranho', async () => {
    const detect = vi.fn(async () => env({ mode: 'docker' }))
    const cache = createOllamaEnvCache(detect)
    cache.invalidate()
    expect((await cache.shared()).mode).toBe('docker')
    expect(detect).toHaveBeenCalledOnce()
  })

  it('detecção que falha não derruba o cache nem trava as seguintes', async () => {
    const detect = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(env({ mode: 'docker' }))
    const cache = createOllamaEnvCache(detect)
    await expect(cache.shared()).rejects.toThrow('boom')
    expect(cache.get()).toBeNull()
    expect((await cache.shared()).mode).toBe('docker')
  })
})

describe('ollamaFollowUps', () => {
  function job(kind: JobView['kind'], state: JobView['state']): JobView {
    return { kind, state, finishedAt: '2026-09-23T10:00:00.000Z' } as JobView
  }

  it('qualquer tarefa ollama-* em qualquer estado final reseta o cache', () => {
    for (const state of ['done', 'failed', 'cancelled'] as const) {
      expect(ollamaFollowUps([job('ollama-stop', state)]).resetCache).toBe(true)
    }
    expect(ollamaFollowUps([job('update', 'done')]).resetCache).toBe(false)
    expect(ollamaFollowUps([]).resetCache).toBe(false)
  })

  it('só troca de modo concluída grava o modo preferido', () => {
    expect(ollamaFollowUps([job('ollama-use-native', 'done')]).persistMode).toBe('native')
    expect(ollamaFollowUps([job('ollama-use-docker', 'done')]).persistMode).toBe('docker')
    expect(ollamaFollowUps([job('ollama-use-native', 'failed')]).persistMode).toBeNull()
    expect(ollamaFollowUps([job('ollama-use-docker', 'cancelled')]).persistMode).toBeNull()
    expect(ollamaFollowUps([job('ollama-start', 'done')]).persistMode).toBeNull()
  })

  it('duas trocas no mesmo lote: vale a que terminou por último', () => {
    const older = { ...job('ollama-use-native', 'done'), finishedAt: '2026-09-23T10:00:00.000Z' }
    const newer = { ...job('ollama-use-docker', 'done'), finishedAt: '2026-09-23T10:00:05.000Z' }
    // `queue.list()` põe as terminadas da mais recente para a mais antiga; a ordem não importa.
    expect(ollamaFollowUps([newer, older]).persistMode).toBe('docker')
    expect(ollamaFollowUps([older, newer]).persistMode).toBe('docker')
  })
})

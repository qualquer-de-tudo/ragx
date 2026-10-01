import { describe, expect, it } from 'vitest'
import type { ExecFn, ExecResult } from '../../system/exec'
import { createOllamaEnvCache } from '../wiring'
import { DOCKER_RETRY_MS, detectOllama, detectOllamaLight } from '../environment'
import type { EnvDeps, LightState } from '../environment'
import type { OllamaEnvironment } from '../../../src/types/ragx-bridge'

const ok = (stdout = ''): ExecResult => ({ code: 0, stdout, stderr: '' })
const fail: ExecResult = { code: 1, stdout: '', stderr: 'erro' }
const NOT_FOUND: ExecResult = { code: -1, stdout: '', stderr: 'ENOENT', notFound: true }

const DOCKER_PS = 'docker ps -a --filter name=^ollama$ --format {{.State}}'
const TASKLIST = 'tasklist /FI IMAGENAME eq ollama.exe /FO CSV /NH'
const RUNNING_PROCESS = '"ollama.exe","1234","Console","1","50.000 K"'

interface Scenario {
  responses?: Record<string, ExecResult>
  api?: unknown
  nativePath?: string | null
}

/** Dependências com um registro de TODO comando executado, para contar processos. */
function setup(s: Scenario = {}) {
  const calls: string[] = []
  const state = { responses: s.responses ?? {}, api: s.api, nativePath: s.nativePath ?? null }
  const exec: ExecFn = async (file, args) => {
    const key = [file, ...args].join(' ')
    calls.push(key)
    return state.responses[key] ?? NOT_FOUND
  }
  const d: EnvDeps = {
    exec,
    httpGetJson: async () => (state.api === undefined ? null : state.api),
    platform: 'win32',
    arch: 'x64',
    resolveNativePath: () => state.nativePath,
    gpuNames: async () => [],
  }
  return { d, calls, state }
}

describe('detectOllama - um único docker ps (RAGX-0173)', () => {
  it('Docker de pé: um só comando de docker, e não três', async () => {
    const { d, calls } = setup({ responses: { [DOCKER_PS]: ok('running\n') } })
    await detectOllama(d)
    expect(calls.filter((c) => c.startsWith('docker'))).toEqual([DOCKER_PS])
  })

  it('ENOENT = não instalado; código diferente de zero = instalado e parado', async () => {
    expect((await detectOllama(setup().d)).docker).toEqual({ installed: false, running: false })
    expect((await detectOllama(setup({ responses: { [DOCKER_PS]: fail } }).d)).docker).toEqual({
      installed: true,
      running: false,
    })
  })

  it('container ausente, parado e rodando', async () => {
    const run = async (out: string) => (await detectOllama(setup({ responses: { [DOCKER_PS]: ok(out) } }).d)).container
    expect(await run('\n')).toEqual({ exists: false, running: false })
    expect(await run('exited\n')).toEqual({ exists: true, running: false })
    expect(await run('running\n')).toEqual({ exists: true, running: true })
  })
})

describe('detectOllamaLight', () => {
  const noState = (): LightState => ({ lastDockerProbeAt: null })

  async function previous(s: Scenario = {}): Promise<OllamaEnvironment> {
    return detectOllama(setup(s).d)
  }

  it('sem detecção anterior é a completa', async () => {
    const { d, calls } = setup({ responses: { [DOCKER_PS]: ok('') } })
    const state = noState()
    const env = await detectOllamaLight(d, null, state, () => 1000)
    expect(env.docker.installed).toBe(true)
    expect(calls).toContain(DOCKER_PS)
    expect(state.lastDockerProbeAt).toBe(1000)
  })

  it('API no ar, sem container e sem Docker: ZERO processos; native.running é inferido true', async () => {
    const prev = await previous({ api: { models: [] } })
    const { d, calls } = setup({ api: { models: [{ name: 'a' }] }, nativePath: 'C:\\o.exe' })
    const env = await detectOllamaLight(d, prev, { lastDockerProbeAt: 0 }, () => 10_000)
    expect(calls).toEqual([])
    expect(env.native.running).toBe(true)
    expect(env.mode).toBe('native')
    expect(env.models).toEqual(['a'])
  })

  it('Docker de pé na detecção anterior: 1 processo (docker ps) por tick; sem tasklist enquanto não há suspeita', async () => {
    const prev = await previous({ responses: { [DOCKER_PS]: ok('exited\n') }, api: { models: [] } })
    const { d, calls } = setup({ responses: { [DOCKER_PS]: ok('exited\n') }, api: { models: [] }, nativePath: 'C:\\o.exe' })
    const env = await detectOllamaLight(d, prev, { lastDockerProbeAt: 5 }, () => 6)
    expect(calls).toEqual([DOCKER_PS])
    expect(env.container).toEqual({ exists: true, running: false })
    expect(env.native.running).toBe(true) // API no ar e container parado: inferido
  })

  it('API no ar E container rodando é suspeita de conflito: confirma com o tasklist', async () => {
    const prev = await previous({ responses: { [DOCKER_PS]: ok('running\n') }, api: { models: [] } })
    const s = setup({ responses: { [DOCKER_PS]: ok('running\n'), [TASKLIST]: ok(RUNNING_PROCESS) }, api: { models: [] }, nativePath: 'C:\\o.exe' })
    const env = await detectOllamaLight(s.d, prev, { lastDockerProbeAt: 5 }, () => 6)
    expect(s.calls).toEqual([DOCKER_PS, TASKLIST])
    expect(env.mode).toBe('conflict')

    const so = setup({ responses: { [DOCKER_PS]: ok('running\n'), [TASKLIST]: ok('INFO: nenhum') }, api: { models: [] }, nativePath: 'C:\\o.exe' })
    expect((await detectOllamaLight(so.d, prev, { lastDockerProbeAt: 5 }, () => 6)).mode).toBe('docker')
  })

  it('API fora do ar: tasklist só se há Ollama nativo instalado', async () => {
    const prev = await previous()
    const semNativo = setup({})
    expect((await detectOllamaLight(semNativo.d, prev, { lastDockerProbeAt: 0 }, () => 1)).mode).toBe('none')
    expect(semNativo.calls.filter((c) => c.startsWith('tasklist'))).toEqual([])

    const comNativo = setup({ nativePath: 'C:\\o.exe', responses: { [TASKLIST]: ok(RUNNING_PROCESS) } })
    const env = await detectOllamaLight(comNativo.d, prev, { lastDockerProbeAt: 0 }, () => 1)
    expect(comNativo.calls).toContain(TASKLIST)
    expect(env.native.running).toBe(true)
  })

  it('Docker ausente ou parado: repete o docker ps só a cada 5 minutos', async () => {
    const prev = await previous() // Docker ausente
    const state: LightState = { lastDockerProbeAt: 1_000_000 }
    const s = setup({})
    await detectOllamaLight(s.d, prev, state, () => 1_000_000 + 60_000) // 1 min depois
    await detectOllamaLight(s.d, prev, state, () => 1_000_000 + 4 * 60_000)
    expect(s.calls.filter((c) => c === DOCKER_PS)).toEqual([])
    await detectOllamaLight(s.d, prev, state, () => 1_000_000 + DOCKER_RETRY_MS)
    expect(s.calls.filter((c) => c === DOCKER_PS)).toHaveLength(1)
    expect(state.lastDockerProbeAt).toBe(1_000_000 + DOCKER_RETRY_MS)
  })

  it('o Docker que passou a existir é visto na próxima janela de 5 minutos', async () => {
    const prev = await previous()
    const s = setup({ responses: { [DOCKER_PS]: ok('running\n') } })
    const env = await detectOllamaLight(s.d, prev, { lastDockerProbeAt: 0 }, () => DOCKER_RETRY_MS + 1)
    expect(env.docker).toEqual({ installed: true, running: true })
    expect(env.container.running).toBe(true)
  })

  it('para os mesmos fatos, a leve responde o mesmo que a completa (modos docker, native, conflict e none)', async () => {
    const cenarios: Scenario[] = [
      { responses: { [DOCKER_PS]: ok('running\n') }, api: { models: [] } }, // docker
      { api: { models: [] }, nativePath: 'C:\\o.exe', responses: { [TASKLIST]: ok(RUNNING_PROCESS) } }, // native
      { responses: { [DOCKER_PS]: ok('running\n'), [TASKLIST]: ok(RUNNING_PROCESS) }, api: { models: [] }, nativePath: 'C:\\o.exe' }, // conflict
      {}, // none
    ]
    for (const c of cenarios) {
      const completa = await detectOllama(setup(c).d)
      const leve = await detectOllamaLight(setup(c).d, completa, { lastDockerProbeAt: 0 }, () => 1)
      expect(leve.mode).toBe(completa.mode)
      expect(leve.docker).toEqual(completa.docker)
      expect(leve.container).toEqual(completa.container)
      expect(leve.native.running).toBe(completa.native.running)
      expect(leve.apiUp).toBe(completa.apiUp)
    }
  })

  it('nunca lança, mesmo com tudo falhando', async () => {
    const prev = await previous()
    const d: EnvDeps = {
      exec: async () => {
        throw new Error('boom')
      },
      httpGetJson: async () => {
        throw new Error('boom')
      },
      platform: 'win32',
      arch: 'x64',
      resolveNativePath: () => {
        throw new Error('boom')
      },
    }
    await expect(detectOllamaLight(d, prev, { lastDockerProbeAt: 0 }, () => DOCKER_RETRY_MS * 2)).resolves.toMatchObject({ mode: 'none' })
  })
})

describe('createOllamaEnvCache.light', () => {
  const env = (mode: OllamaEnvironment['mode']): OllamaEnvironment =>
    ({ mode, apiUp: false, models: [] }) as unknown as OllamaEnvironment

  it('sem detecção leve configurada, é a completa', async () => {
    let completas = 0
    const cache = createOllamaEnvCache(async () => {
      completas += 1
      return env('none')
    })
    await cache.light()
    expect(completas).toBe(1)
  })

  it('a leve parte do último ambiente e o atualiza; `fresh` continua sendo a completa', async () => {
    const anteriores: Array<OllamaEnvironment | null> = []
    let completas = 0
    const cache = createOllamaEnvCache(
      async () => {
        completas += 1
        return env('docker')
      },
      async (previous) => {
        anteriores.push(previous)
        return env('native')
      },
    )
    await cache.fresh()
    await cache.light()
    expect(anteriores).toEqual([env('docker')])
    expect(cache.get()?.mode).toBe('native')
    expect(completas).toBe(1)
  })

  it('o tick leve junta-se a uma detecção completa em andamento em vez de atropelá-la', async () => {
    let liberar: (e: OllamaEnvironment) => void = () => {}
    let leves = 0
    const cache = createOllamaEnvCache(
      () => new Promise<OllamaEnvironment>((r) => (liberar = r)),
      async () => {
        leves += 1
        return env('native')
      },
    )
    const completa = cache.fresh()
    const leve = cache.light()
    await new Promise((resolve) => setTimeout(resolve, 0)) // `detect` roda num microtask depois
    liberar(env('docker'))
    expect((await leve).mode).toBe('docker')
    await completa
    expect(leves).toBe(0)
  })
})

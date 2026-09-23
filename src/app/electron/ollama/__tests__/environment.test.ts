import { describe, expect, it } from 'vitest'
import type { ExecFn, ExecResult } from '../../system/exec'
import { classifyGpu, detectOllama, recommend } from '../environment'
import type { EnvDeps } from '../environment'
import type { OllamaEnvironment } from '../../../src/types/ragx-bridge'

const ok = (stdout = ''): ExecResult => ({ code: 0, stdout, stderr: '' })
const fail: ExecResult = { code: 1, stdout: '', stderr: 'erro' }

const PS_GPU = 'powershell -NoProfile -NonInteractive -Command (Get-CimInstance Win32_VideoController).Name'
const DOCKER_VERSION = 'docker --version'
const DOCKER_INFO = 'docker info --format {{.ServerVersion}}'
const DOCKER_PS = 'docker ps -a --filter name=^ollama$ --format {{.State}}'
const TASKLIST = 'tasklist /FI IMAGENAME eq ollama.exe /FO CSV /NH'
const PGREP = 'pgrep -x ollama'

interface Opts {
  responses?: Record<string, ExecResult>
  api?: unknown
  platform?: NodeJS.Platform
  arch?: string
  nativePath?: string | null
}

function deps(o: Opts = {}): EnvDeps {
  const map = o.responses ?? {}
  const exec: ExecFn = async (file, args) => map[[file, ...args].join(' ')] ?? fail
  return {
    exec,
    httpGetJson: async () => (o.api === undefined ? null : o.api),
    platform: o.platform ?? 'win32',
    arch: o.arch ?? 'x64',
    resolveNativePath: () => (o.nativePath === undefined ? null : o.nativePath),
  }
}

describe('classifyGpu', () => {
  it('nvidia', () => {
    expect(classifyGpu(['NVIDIA GeForce RTX 4070'], 'win32', 'x64')).toEqual({ vendor: 'nvidia', name: 'NVIDIA GeForce RTX 4070' })
  })
  it('amd', () => {
    expect(classifyGpu(['AMD Radeon RX 7700 XT'], 'win32', 'x64')).toEqual({ vendor: 'amd', name: 'AMD Radeon RX 7700 XT' })
  })
  it('nvidia vence intel', () => {
    expect(classifyGpu(['Intel(R) UHD Graphics', 'NVIDIA GeForce GTX 1650'], 'win32', 'x64')).toEqual({
      vendor: 'nvidia',
      name: 'NVIDIA GeForce GTX 1650',
    })
  })
  it('intel', () => {
    expect(classifyGpu(['Intel(R) UHD Graphics'], 'win32', 'x64')).toEqual({ vendor: 'intel', name: 'Intel(R) UHD Graphics' })
  })
  it('lista vazia é none', () => {
    expect(classifyGpu([], 'win32', 'x64')).toEqual({ vendor: 'none', name: null })
  })
  it('sem correspondência é unknown', () => {
    expect(classifyGpu(['Microsoft Basic Display Adapter'], 'win32', 'x64')).toEqual({
      vendor: 'unknown',
      name: 'Microsoft Basic Display Adapter',
    })
  })
  it('macOS arm64 é apple', () => {
    expect(classifyGpu([], 'darwin', 'arm64').vendor).toBe('apple')
  })
  it('macOS x64 é unknown', () => {
    expect(classifyGpu([], 'darwin', 'x64').vendor).toBe('unknown')
  })
})

type Base = Omit<OllamaEnvironment, 'recommendation'>
function base(over: Partial<Base> = {}): Base {
  return {
    platform: 'win32',
    gpu: { vendor: 'none', name: null },
    docker: { installed: false, running: false },
    container: { exists: false, running: false },
    native: { installed: false, path: null, running: false },
    canInstallNative: true,
    apiUp: false,
    models: [],
    mode: 'none',
    ...over,
  }
}

describe('recommend', () => {
  it('macOS', () => {
    expect(recommend(base({ platform: 'darwin', gpu: { vendor: 'apple', name: null } }))).toEqual({
      mode: 'native',
      reason: 'No macOS o Docker não usa a GPU. O Ollama local usa a GPU do Mac.',
    })
  })
  it('NVIDIA com Docker instalado', () => {
    expect(recommend(base({ gpu: { vendor: 'nvidia', name: 'x' }, docker: { installed: true, running: false } }))).toEqual({
      mode: 'docker',
      reason: 'O container consegue usar sua GPU NVIDIA.',
    })
  })
  it('NVIDIA sem Docker', () => {
    expect(recommend(base({ gpu: { vendor: 'nvidia', name: 'x' } }))).toEqual({
      mode: 'native',
      reason: 'Sem Docker instalado, o Ollama local usa sua GPU NVIDIA.',
    })
  })
  it('AMD', () => {
    expect(recommend(base({ gpu: { vendor: 'amd', name: 'x' }, docker: { installed: true, running: true } }))).toEqual({
      mode: 'native',
      reason: 'O Docker não repassa GPU AMD. O Ollama local usa a sua placa.',
    })
  })
  it('demais com Docker instalado (parado conta como instalado)', () => {
    expect(recommend(base({ gpu: { vendor: 'intel', name: 'x' }, docker: { installed: true, running: false } }))).toEqual({
      mode: 'docker',
      reason: 'Sem GPU compatível com o Docker, o container resolve e isola o Ollama.',
    })
  })
  it('demais sem Docker', () => {
    expect(recommend(base({ gpu: { vendor: 'none', name: null } }))).toEqual({
      mode: 'native',
      reason: 'Sem Docker instalado, use o Ollama local.',
    })
  })
})

describe('detectOllama', () => {
  const dockerUp = { [DOCKER_VERSION]: ok('Docker version 27'), [DOCKER_INFO]: ok('27.0.1') }

  it('Docker ausente', async () => {
    const env = await detectOllama(deps({ responses: { [PS_GPU]: ok('NVIDIA GeForce RTX 4070\r\n') } }))
    expect(env.docker).toEqual({ installed: false, running: false })
    expect(env.container).toEqual({ exists: false, running: false })
    expect(env.mode).toBe('none')
    expect(env.gpu.vendor).toBe('nvidia')
    expect(env.recommendation.mode).toBe('native')
    expect(env.canInstallNative).toBe(true)
  })

  it('Docker instalado mas parado', async () => {
    const env = await detectOllama(deps({ responses: { [DOCKER_VERSION]: ok('Docker version 27') } }))
    expect(env.docker).toEqual({ installed: true, running: false })
    expect(env.container.exists).toBe(false)
    expect(env.recommendation.mode).toBe('docker')
  })

  it('container inexistente', async () => {
    const env = await detectOllama(deps({ responses: { ...dockerUp, [DOCKER_PS]: ok('\n') } }))
    expect(env.docker).toEqual({ installed: true, running: true })
    expect(env.container).toEqual({ exists: false, running: false })
    expect(env.mode).toBe('none')
  })

  it('container parado', async () => {
    const env = await detectOllama(deps({ responses: { ...dockerUp, [DOCKER_PS]: ok('exited\n') } }))
    expect(env.container).toEqual({ exists: true, running: false })
    expect(env.mode).toBe('none')
  })

  it('container rodando com API no ar', async () => {
    const env = await detectOllama(
      deps({
        responses: { ...dockerUp, [DOCKER_PS]: ok('running\n') },
        api: { models: [{ name: 'nomic-embed-text:latest' }, { name: 'bge-m3' }, {}] },
      }),
    )
    expect(env.container).toEqual({ exists: true, running: true })
    expect(env.apiUp).toBe(true)
    expect(env.models).toEqual(['nomic-embed-text:latest', 'bge-m3'])
    expect(env.mode).toBe('docker')
  })

  it('nativo rodando (Windows)', async () => {
    const env = await detectOllama(
      deps({
        responses: { [TASKLIST]: ok('"ollama.exe","1234","Console","1","50.000 K"\r\n') },
        nativePath: 'C:\\Ollama\\ollama.exe',
        api: { models: [] },
      }),
    )
    expect(env.native).toEqual({ installed: true, path: 'C:\\Ollama\\ollama.exe', running: true })
    expect(env.mode).toBe('native')
  })

  it('tasklist sem o processo não conta como rodando', async () => {
    const env = await detectOllama(
      deps({
        responses: { [TASKLIST]: ok('INFO: No tasks are running which match the specified criteria.') },
        nativePath: 'C:\\o.exe',
      }),
    )
    expect(env.native).toEqual({ installed: true, path: 'C:\\o.exe', running: false })
    expect(env.mode).toBe('none')
  })

  it('nativo rodando (Linux, pgrep)', async () => {
    const env = await detectOllama(
      deps({ platform: 'linux', responses: { [PGREP]: ok('99\n') }, nativePath: '/usr/local/bin/ollama' }),
    )
    expect(env.native.running).toBe(true)
    expect(env.canInstallNative).toBe(false)
    expect(env.mode).toBe('native')
  })

  it('os dois rodando é conflict', async () => {
    const env = await detectOllama(
      deps({
        responses: { ...dockerUp, [DOCKER_PS]: ok('running'), [TASKLIST]: ok('"ollama.exe","1"') },
        nativePath: 'C:\\o.exe',
        api: { models: [] },
      }),
    )
    expect(env.mode).toBe('conflict')
  })

  it('nada é none', async () => {
    const env = await detectOllama(deps())
    expect(env.mode).toBe('none')
    expect(env.apiUp).toBe(false)
    expect(env.models).toEqual([])
    expect(env.gpu).toEqual({ vendor: 'none', name: null })
  })

  it('API no ar sem container e sem processo nativo detectado é native', async () => {
    const env = await detectOllama(deps({ api: { models: [{ name: 'a' }] } }))
    expect(env.apiUp).toBe(true)
    expect(env.native.running).toBe(false)
    expect(env.mode).toBe('native')
  })

  it('exec que lança para tudo devolve ambiente vazio sem rejeitar', async () => {
    const d = deps()
    d.exec = async () => {
      throw new Error('boom')
    }
    d.httpGetJson = async () => {
      throw new Error('boom')
    }
    d.resolveNativePath = () => {
      throw new Error('boom')
    }
    const env = await detectOllama(d)
    expect(env.docker).toEqual({ installed: false, running: false })
    expect(env.container).toEqual({ exists: false, running: false })
    expect(env.native).toEqual({ installed: false, path: null, running: false })
    expect(env.apiUp).toBe(false)
    expect(env.mode).toBe('none')
    expect(env.gpu.vendor).toBe('none')
  })

  it('Linux lista GPU via lspci filtrando VGA/3D/Display', async () => {
    const lspci = [
      '00:02.0 VGA compatible controller: Intel Corporation UHD Graphics',
      '01:00.0 3D controller: NVIDIA Corporation GA107 [GeForce RTX 3050]',
      '02:00.0 Ethernet controller: Realtek',
    ].join('\n')
    const env = await detectOllama(deps({ platform: 'linux', responses: { lspci: ok(lspci) } }))
    expect(env.gpu.vendor).toBe('nvidia')
  })

  it('macOS arm64 é apple sem consultar nada', async () => {
    const env = await detectOllama(deps({ platform: 'darwin', arch: 'arm64' }))
    expect(env.gpu.vendor).toBe('apple')
    expect(env.recommendation.mode).toBe('native')
  })
})

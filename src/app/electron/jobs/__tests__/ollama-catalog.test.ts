import { describe, expect, it } from 'vitest'
import { resolveJob, JobRejected, type CatalogContext } from '../catalog'
import type { JobRequest, OllamaEnvironment } from '../../../src/types/ragx-bridge'

function ctx(over: Partial<CatalogContext> = {}): CatalogContext {
  return { projectById: () => undefined, folderByToken: () => undefined, ...over }
}

function env(over: Partial<OllamaEnvironment> = {}): OllamaEnvironment {
  return {
    platform: 'win32',
    gpu: { vendor: 'none', name: null },
    docker: { installed: true, running: true },
    container: { exists: true, running: true },
    native: { installed: false, path: null, running: false },
    canInstallNative: true,
    apiUp: true,
    models: [],
    mode: 'docker',
    recommendation: { mode: 'docker', reason: 'x' },
    ...over,
  }
}

const P = { cwd: null, progress: false }
const SERVE = {
  cmd: 'ollama',
  args: ['serve'],
  ...P,
  detached: true,
  when: 'native-not-running',
  skipNote: 'O Ollama local já estava rodando.',
}
const WAIT = { cmd: 'ollama', args: [], ...P, waitForOllamaApi: { timeoutMs: 60000 } }

describe('resolveJob - ollama-use-native', () => {
  it('ambiente docker em uso: cinco passos na ordem, com when corretos', () => {
    const job = resolveJob(
      { kind: 'ollama-use-native' },
      ctx({ ollamaEnv: () => env(), requiredModels: () => ['nomic-embed-text'] }),
    )
    expect(job.label).toBe('Usar o Ollama local')
    expect(job.model).toBeNull()
    expect(job.dedupeKey).toBe('ollama-use-native||')
    expect(job.steps).toEqual([
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
      {
        cmd: 'winget',
        args: [
          'install',
          '-e',
          '--id',
          'Ollama.Ollama',
          '--silent',
          '--accept-package-agreements',
          '--accept-source-agreements',
        ],
        ...P,
        when: 'native-missing',
      },
      SERVE,
      WAIT,
      { cmd: 'ollama', args: ['pull', 'nomic-embed-text'], ...P },
    ])
  })

  it('dois modelos requeridos geram dois pulls', () => {
    const job = resolveJob(
      { kind: 'ollama-use-native' },
      ctx({ ollamaEnv: () => env(), requiredModels: () => ['a', 'b:1'] }),
    )
    expect(job.steps.slice(4)).toEqual([
      { cmd: 'ollama', args: ['pull', 'a'], ...P },
      { cmd: 'ollama', args: ['pull', 'b:1'], ...P },
    ])
  })

  it('modelo inválido na lista é ignorado com nota e nunca vira argumento', () => {
    const job = resolveJob(
      { kind: 'ollama-use-native' },
      ctx({ ollamaEnv: () => env(), requiredModels: () => ['x; rm -rf /', '--help', 'ok-model'] }),
    )
    expect(job.steps.slice(4)).toEqual([{ cmd: 'ollama', args: ['pull', 'ok-model'], ...P }])
    expect(job.steps.flatMap((s) => s.args)).not.toContain('--help')
    expect(job.notes).toHaveLength(2)
  })

  it('fora do Windows sem nativo instalado: recusa', () => {
    const e = env({ platform: 'linux', canInstallNative: false })
    expect(() => resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => e }))).toThrow(
      'A instalação automática do Ollama só existe no Windows. Baixe em https://ollama.com/download e abra o painel de novo.',
    )
  })

  it('fora do Windows com nativo instalado: aceita', () => {
    const e = env({
      platform: 'linux',
      canInstallNative: false,
      native: { installed: true, path: '/usr/bin/ollama', running: false },
    })
    expect(resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => e })).steps.length).toBeGreaterThanOrEqual(4)
  })
})

describe('resolveJob - ollama-use-docker', () => {
  const TASKKILLS = [
    { cmd: 'taskkill', args: ['/IM', 'ollama app.exe', '/T', '/F'], ...P, when: 'native-running', okExitCodes: [128] },
    { cmd: 'taskkill', args: ['/IM', 'ollama.exe', '/T', '/F'], ...P, when: 'native-running', okExitCodes: [128] },
  ]
  const RUN_BASE = [
    'run',
    '-d',
    '--name',
    'ollama',
    '-p',
    '11434:11434',
    '-v',
    'ollama:/root/.ollama',
    '--restart',
    'unless-stopped',
  ]

  it('Windows sem NVIDIA: dois taskkill, start, run sem --gpus, espera e pull', () => {
    const job = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => env(), requiredModels: () => ['m1'] }))
    expect(job.label).toBe('Usar o Ollama no Docker')
    expect(job.dedupeKey).toBe('ollama-use-docker||')
    expect(job.steps).toEqual([
      ...TASKKILLS,
      { cmd: 'docker', args: ['start', 'ollama'], ...P, when: 'container-exists' },
      { cmd: 'docker', args: [...RUN_BASE, 'ollama/ollama'], ...P, when: 'container-missing' },
      WAIT,
      { cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'm1'], ...P },
    ])
  })

  it('Linux: pkill -x ollama no lugar dos taskkill', () => {
    const job = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => env({ platform: 'linux' }) }))
    expect(job.steps[0]).toEqual({ cmd: 'pkill', args: ['-x', 'ollama'], ...P, when: 'native-running', okExitCodes: [1] })
    expect(job.steps.some((s) => s.cmd === 'taskkill')).toBe(false)
  })

  it('NVIDIA: --gpus all presente e antes da imagem', () => {
    const job = resolveJob(
      { kind: 'ollama-use-docker' },
      ctx({ ollamaEnv: () => env({ gpu: { vendor: 'nvidia', name: 'RTX' } }) }),
    )
    const run = job.steps.find((s) => s.when === 'container-missing')
    expect(run?.args).toEqual([...RUN_BASE, '--gpus', 'all', 'ollama/ollama'])
    expect(run!.args.indexOf('--gpus')).toBeLessThan(run!.args.indexOf('ollama/ollama'))
  })

  it('AMD: sem --gpus', () => {
    const job = resolveJob(
      { kind: 'ollama-use-docker' },
      ctx({ ollamaEnv: () => env({ gpu: { vendor: 'amd', name: 'RX' } }) }),
    )
    expect(job.steps.find((s) => s.when === 'container-missing')?.args).not.toContain('--gpus')
  })

  it('recusa sem Docker instalado', () => {
    const e = env({ docker: { installed: false, running: false } })
    expect(() => resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => e }))).toThrow(
      'O Docker não está instalado nesta máquina.',
    )
  })
})

describe('resolveJob - ollama-stop', () => {
  it('Windows', () => {
    const job = resolveJob({ kind: 'ollama-stop' }, ctx({ ollamaEnv: () => env() }))
    expect(job.label).toBe('Parar o Ollama')
    expect(job.dedupeKey).toBe('ollama-stop||')
    expect(job.steps).toEqual([
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
      { cmd: 'taskkill', args: ['/IM', 'ollama app.exe', '/T', '/F'], ...P, when: 'native-running', okExitCodes: [128] },
      { cmd: 'taskkill', args: ['/IM', 'ollama.exe', '/T', '/F'], ...P, when: 'native-running', okExitCodes: [128] },
    ])
  })

  it('Linux', () => {
    const job = resolveJob({ kind: 'ollama-stop' }, ctx({ ollamaEnv: () => env({ platform: 'linux' }) }))
    expect(job.steps).toEqual([
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
      { cmd: 'pkill', args: ['-x', 'ollama'], ...P, when: 'native-running', okExitCodes: [1] },
    ])
  })
})

describe('resolveJob - ollama-start segue o ambiente', () => {
  it('container existente: docker start condicionado', () => {
    const e = env({ container: { exists: true, running: false } })
    const job = resolveJob({ kind: 'ollama-start' }, ctx({ ollamaEnv: () => e }))
    expect(job.steps).toEqual([{ cmd: 'docker', args: ['start', 'ollama'], ...P, when: 'container-exists' }])
  })

  it('só nativo instalado: serve destacado e espera da API', () => {
    const e = env({
      container: { exists: false, running: false },
      native: { installed: true, path: 'x', running: false },
      mode: 'native',
    })
    expect(resolveJob({ kind: 'ollama-start' }, ctx({ ollamaEnv: () => e })).steps).toEqual([SERVE, WAIT])
  })

  it('sem ollamaEnv: comportamento antigo', () => {
    expect(resolveJob({ kind: 'ollama-start' }, ctx()).steps).toEqual([
      { cmd: 'docker', args: ['start', 'ollama'], ...P },
    ])
  })
})

describe('resolveJob - ollama-pull segue o modo', () => {
  it('native: ollama pull', () => {
    const job = resolveJob(
      { kind: 'ollama-pull', model: 'nomic-embed-text' },
      ctx({ ollamaEnv: () => env({ mode: 'native' }) }),
    )
    expect(job.steps).toEqual([{ cmd: 'ollama', args: ['pull', 'nomic-embed-text'], ...P }])
    expect(job.model).toBe('nomic-embed-text')
  })

  it('docker e sem ambiente: docker exec', () => {
    const expected = [{ cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'nomic-embed-text'], ...P }]
    const req: JobRequest = { kind: 'ollama-pull', model: 'nomic-embed-text' }
    expect(resolveJob(req, ctx({ ollamaEnv: () => env() })).steps).toEqual(expected)
    expect(resolveJob(req, ctx()).steps).toEqual(expected)
  })

  it('recusa modelo malicioso nos dois modos', () => {
    for (const mode of ['native', 'docker'] as const) {
      const c = ctx({ ollamaEnv: () => env({ mode }) })
      expect(() => resolveJob({ kind: 'ollama-pull', model: 'x; rm -rf /' }, c)).toThrow(JobRejected)
      expect(() => resolveJob({ kind: 'ollama-pull', model: '--help' }, c)).toThrow(JobRejected)
    }
  })
})

describe('resolveJob - catálogo fechado', () => {
  it('kinds novos passam e kind inventado é recusado', () => {
    for (const kind of ['ollama-use-native', 'ollama-use-docker', 'ollama-stop'] as const) {
      expect(resolveJob({ kind }, ctx()).kind).toBe(kind)
    }
    expect(() => resolveJob({ kind: 'ollama-nuke' } as unknown as JobRequest, ctx())).toThrow(JobRejected)
  })
})

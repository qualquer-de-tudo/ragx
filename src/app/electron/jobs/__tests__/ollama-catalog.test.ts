import { describe, expect, it } from 'vitest'
import { resolveJob, JobRejected, STOP_NATIVE_WINDOWS_SCRIPT, type CatalogContext } from '../catalog'
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
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
      SERVE,
      WAIT,
      { cmd: 'ollama', args: ['pull', 'nomic-embed-text'], ...P },
    ])
  })

  it('instala antes de parar o container: uma falha do winget nunca deixa a máquina sem Ollama', () => {
    const steps = resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => env() })).steps
    const winget = steps.findIndex((s) => s.cmd === 'winget')
    const stop = steps.findIndex((s) => s.cmd === 'docker' && s.args[0] === 'stop')
    expect(winget).toBeGreaterThanOrEqual(0)
    expect(winget).toBeLessThan(stop)
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
    const steps = resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => e })).steps
    expect(steps).toEqual([
      expect.objectContaining({ cmd: 'winget', when: 'native-missing' }),
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
      SERVE,
      WAIT,
    ])
  })

  it('modo conflict: mesmos passos do docker em uso (as condições cobrem)', () => {
    const conflict = env({ mode: 'conflict', native: { installed: true, path: 'x', running: true } })
    const a = resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => conflict }))
    const b = resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => env() }))
    expect(a.steps).toEqual(b.steps)
  })
})

describe('resolveJob - ollama-use-docker', () => {
  const NATIVE_EXE = 'C:\\Users\\ana\\AppData\\Local\\Programs\\Ollama\\ollama.exe'
  const NATIVE_DIR = 'C:\\Users\\ana\\AppData\\Local\\Programs\\Ollama'
  const withNative = (over: Partial<OllamaEnvironment> = {}): OllamaEnvironment =>
    env({ native: { installed: true, path: NATIVE_EXE, running: true }, ...over })
  const STOP_NATIVE_WIN = {
    cmd: 'powershell',
    args: ['-NoProfile', '-NonInteractive', '-Command', STOP_NATIVE_WINDOWS_SCRIPT],
    ...P,
    when: 'native-running',
    env: { OLLAMA_DIR: NATIVE_DIR },
  }
  const PULL_IMAGE = { cmd: 'docker', args: ['pull', 'ollama/ollama'], ...P, when: 'container-missing' }
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

  it('Windows sem NVIDIA: baixa a imagem, para o local, start, run sem --gpus, espera e pull', () => {
    const job = resolveJob(
      { kind: 'ollama-use-docker' },
      ctx({ ollamaEnv: () => withNative(), requiredModels: () => ['m1'] }),
    )
    expect(job.label).toBe('Usar o Ollama no Docker')
    expect(job.dedupeKey).toBe('ollama-use-docker||')
    expect(job.steps).toEqual([
      PULL_IMAGE,
      STOP_NATIVE_WIN,
      { cmd: 'docker', args: ['start', 'ollama'], ...P, when: 'container-exists' },
      { cmd: 'docker', args: [...RUN_BASE, 'ollama/ollama'], ...P, when: 'container-missing' },
      WAIT,
      { cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'm1'], ...P },
    ])
  })

  it('a imagem é baixada antes de parar o Ollama local', () => {
    const steps = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => withNative() })).steps
    const pull = steps.findIndex((s) => s.cmd === 'docker' && s.args[0] === 'pull')
    const stop = steps.findIndex((s) => s.when === 'native-running')
    expect(pull).toBeGreaterThanOrEqual(0)
    expect(pull).toBeLessThan(stop)
  })

  it('Windows: o caminho do Ollama local só vai pelo ambiente do processo, nunca dentro do script', () => {
    const steps = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => withNative() })).steps
    const stop = steps.find((s) => s.cmd === 'powershell')!
    expect(stop.env).toEqual({ OLLAMA_DIR: NATIVE_DIR })
    expect(stop.args.join(' ')).not.toContain(NATIVE_DIR)
    expect(stop.args.join(' ')).not.toContain('Programs')
    expect(STOP_NATIVE_WINDOWS_SCRIPT).toContain('$env:OLLAMA_DIR')
    expect(STOP_NATIVE_WINDOWS_SCRIPT).toContain("'ollama.exe'")
    expect(STOP_NATIVE_WINDOWS_SCRIPT).toContain("'ollama app.exe'")
    expect(STOP_NATIVE_WINDOWS_SCRIPT).toContain('Stop-Process')
    expect(STOP_NATIVE_WINDOWS_SCRIPT).toContain('ExecutablePath')
    expect(STOP_NATIVE_WINDOWS_SCRIPT).not.toMatch(/taskkill/i)
    expect(steps.some((s) => (s.cmd as string) === 'taskkill')).toBe(false)
  })

  it('Windows sem caminho do Ollama local: nenhum passo de encerrar', () => {
    const steps = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => env() })).steps
    expect(steps.some((s) => s.cmd === 'powershell' || s.when === 'native-running')).toBe(false)
  })

  it('Linux: pkill -x ollama no lugar do PowerShell', () => {
    const job = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => withNative({ platform: 'linux' }) }))
    expect(job.steps[1]).toEqual({ cmd: 'pkill', args: ['-x', 'ollama'], ...P, when: 'native-running', okExitCodes: [1] })
    expect(job.steps.some((s) => s.cmd === 'powershell')).toBe(false)
  })

  it('NVIDIA: --gpus all presente e antes da imagem', () => {
    const job = resolveJob(
      { kind: 'ollama-use-docker' },
      ctx({ ollamaEnv: () => env({ gpu: { vendor: 'nvidia', name: 'RTX' } }) }),
    )
    const run = job.steps.find((s) => s.args[0] === 'run')
    expect(run?.args).toEqual([...RUN_BASE, '--gpus', 'all', 'ollama/ollama'])
    expect(run!.args.indexOf('--gpus')).toBeLessThan(run!.args.indexOf('ollama/ollama'))
  })

  it('AMD: sem --gpus', () => {
    const job = resolveJob(
      { kind: 'ollama-use-docker' },
      ctx({ ollamaEnv: () => env({ gpu: { vendor: 'amd', name: 'RX' } }) }),
    )
    expect(job.steps.find((s) => s.args[0] === 'run')?.args).not.toContain('--gpus')
  })

  it('recusa sem Docker instalado', () => {
    const e = env({ docker: { installed: false, running: false } })
    expect(() => resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => e }))).toThrow(
      'O Docker não está instalado nesta máquina.',
    )
  })

  it('recusa com o Docker instalado mas parado, antes de parar o Ollama local', () => {
    const e = withNative({ docker: { installed: true, running: false }, container: { exists: false, running: false } })
    expect(() => resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => e }))).toThrow(
      'Abra o Docker Desktop e aguarde ele iniciar.',
    )
  })
})

describe('resolveJob - conflict e model no pedido', () => {
  it('ollama-use-docker em conflict: mesmos passos', () => {
    const native = { installed: true, path: 'C:\\o\\ollama.exe', running: true }
    const conflict = env({ mode: 'conflict', native })
    const a = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => conflict }))
    const b = resolveJob({ kind: 'ollama-use-docker' }, ctx({ ollamaEnv: () => env({ native }) }))
    expect(a.steps).toEqual(b.steps)
  })

  it('model enviado em use-native, use-docker e stop nunca aparece no argv', () => {
    for (const kind of ['ollama-use-native', 'ollama-use-docker', 'ollama-stop'] as const) {
      const job = resolveJob({ kind, model: 'injetado' }, ctx({ ollamaEnv: () => env() }))
      expect(job.steps.flatMap((s) => s.args)).not.toContain('injetado')
      expect(job.model).toBeNull()
    }
  })
})

describe('resolveJob - ollama-stop', () => {
  it('Windows: um só passo de PowerShell, com a pasta do Ollama local pelo ambiente', () => {
    const e = env({ native: { installed: true, path: 'D:\\Apps\\Ollama\\ollama.exe', running: true } })
    const job = resolveJob({ kind: 'ollama-stop' }, ctx({ ollamaEnv: () => e }))
    expect(job.label).toBe('Parar o Ollama')
    expect(job.dedupeKey).toBe('ollama-stop||')
    expect(job.steps).toEqual([
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
      {
        cmd: 'powershell',
        args: ['-NoProfile', '-NonInteractive', '-Command', STOP_NATIVE_WINDOWS_SCRIPT],
        ...P,
        when: 'native-running',
        env: { OLLAMA_DIR: 'D:\\Apps\\Ollama' },
      },
    ])
    expect(job.steps[1].args.join(' ')).not.toContain('D:\\Apps')
  })

  it('Windows sem caminho conhecido: só o docker stop', () => {
    const job = resolveJob({ kind: 'ollama-stop' }, ctx({ ollamaEnv: () => env() }))
    expect(job.steps).toEqual([
      { cmd: 'docker', args: ['stop', 'ollama'], ...P, when: 'container-running', okExitCodes: [] },
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

  describe('preferência de modo', () => {
    const both = (rec: 'docker' | 'native'): OllamaEnvironment =>
      env({
        native: { installed: true, path: 'x', running: false },
        recommendation: { mode: rec, reason: 'x' },
      })
    const start = (e: OllamaEnvironment, pref: 'docker' | 'native' | null) =>
      resolveJob({ kind: 'ollama-start' }, ctx({ ollamaEnv: () => e, preferredOllamaMode: () => pref }))
    const DOCKER = [{ cmd: 'docker', args: ['start', 'ollama'], ...P, when: 'container-exists' }]

    it('preferido nativo com container existente: nativo', () => {
      const job = start(both('docker'), 'native')
      expect(job.steps).toEqual([SERVE, WAIT])
      expect(job.label).toBe('Iniciar o Ollama local')
    })

    it('preferido docker com nativo instalado: docker', () => {
      const job = start(both('native'), 'docker')
      expect(job.steps).toEqual(DOCKER)
      expect(job.label).toBe('Iniciar o container ollama')
    })

    it('preferido indisponível cai na recomendação', () => {
      // preferido docker, sem container: recomendação nativa (instalada) vence.
      const e = env({
        container: { exists: false, running: false },
        native: { installed: true, path: 'x', running: false },
        recommendation: { mode: 'native', reason: 'x' },
      })
      expect(start(e, 'docker').steps).toEqual([SERVE, WAIT])
      // preferido nativo, sem nativo: recomendação docker vence.
      expect(start(env({ recommendation: { mode: 'docker', reason: 'x' } }), 'native').steps).toEqual(DOCKER)
    })

    it('sem preferência: recomendação; recomendação indisponível: o que houver', () => {
      expect(start(both('docker'), null).steps).toEqual(DOCKER)
      expect(start(both('native'), null).steps).toEqual([SERVE, WAIT])
      const onlyContainer = env({ recommendation: { mode: 'native', reason: 'x' } })
      expect(start(onlyContainer, null).steps).toEqual(DOCKER)
    })

    it('falha ao ler o ambiente vira JobRejected', () => {
      const boom = (): never => {
        throw new Error('x')
      }
      expect(() => resolveJob({ kind: 'ollama-start' }, ctx({ ollamaEnv: boom }))).toThrow(JobRejected)
      expect(() =>
        resolveJob({ kind: 'ollama-use-native' }, ctx({ ollamaEnv: () => env(), requiredModels: boom })),
      ).toThrow('Não foi possível ler o ambiente do Ollama.')
      expect(() =>
        resolveJob({ kind: 'ollama-start' }, ctx({ ollamaEnv: () => env(), preferredOllamaMode: boom })),
      ).toThrow(JobRejected)
    })
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

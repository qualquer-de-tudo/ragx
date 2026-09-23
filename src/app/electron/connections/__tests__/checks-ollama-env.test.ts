import { describe, expect, it } from 'vitest'
import { checkAll, checkOllama, type CheckDeps } from '../checks'
import { resolveJob } from '../../jobs/catalog'
import type {
  ConnectionCheck,
  OllamaBenchmark,
  OllamaEnvironment,
  ProjectSnapshot,
  Snapshot,
} from '../../../src/types/ragx-bridge'

function project(): ProjectSnapshot {
  return {
    id: 'p1',
    name: 'p1',
    path: 'C:/p1',
    exists: true,
    embeddingModel: 'nomic-embed-text',
    embeddingProvider: 'ollama',
    visibility: 'workspace',
    counts: { documents: 1, chunks: 2, embeddings: 2, pendingEmbeddings: 0 },
    countsUnavailableReason: null,
    index: null,
    git: null,
    hooksInstalled: null,
    running: null,
    pending: false,
    lastError: null,
    hasStatusFile: true,
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null },
  }
}

const snap1: Snapshot = { projects: [project()], generatedAt: '2026-09-23T10:00:00Z' }

function baseDeps(over: Partial<CheckDeps> = {}): CheckDeps {
  return {
    exec: async () => ({ code: 0, stdout: '', stderr: '' }),
    resolveRagx: () => 'C:/tools/ragx.exe',
    readFile: () => null,
    exists: () => true,
    httpGetJson: async () => null,
    homeDir: 'C:/Users/fulano',
    ...over,
  }
}

function env(over: Partial<OllamaEnvironment> = {}): OllamaEnvironment {
  return {
    platform: 'win32',
    gpu: { vendor: 'nvidia', name: 'NVIDIA RTX 4070' },
    docker: { installed: true, running: true },
    container: { exists: true, running: true },
    native: { installed: false, path: null, running: false },
    canInstallNative: true,
    apiUp: true,
    models: ['nomic-embed-text:latest'],
    mode: 'docker',
    recommendation: { mode: 'docker', reason: 'O container consegue usar sua GPU NVIDIA.' },
    ...over,
  }
}

function bench(over: Partial<OllamaBenchmark> = {}): OllamaBenchmark {
  return {
    ok: true,
    chunksPerSecond: 42.46,
    processor: 'gpu',
    vramMB: 4096,
    model: 'nomic-embed-text',
    measuredAt: '2026-09-23T10:00:00Z',
    error: null,
    ...over,
  }
}

const kinds = (c: ConnectionCheck) => c.actions.map((a) => a.kind)

function assertNoEmDash(c: ConnectionCheck): void {
  const texts = [c.title, c.summary, c.help ?? '', ...c.facts.flatMap((f) => [f.label, f.value]), ...c.actions.map((a) => a.label)]
  for (const t of texts) expect(t).not.toContain('\u2014')
}

const stopped = { exists: false, running: false }

describe('checkOllama com ambiente', () => {
  it('API fora com container parado: iniciar container', async () => {
    const c = await checkOllama(baseDeps(), snap1, env({ apiUp: false, mode: 'none', container: { exists: true, running: false } }))
    expect(c.state).toBe('error')
    expect(c.summary).toBe('O Ollama não está respondendo em localhost:11434.')
    expect(c.actions).toEqual([{ kind: 'ollama-start', label: 'Iniciar container' }])
    expect(c.title).toBe('Ollama')
    assertNoEmDash(c)
  })

  it('API fora com nativo instalado: iniciar o Ollama local', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env({ apiUp: false, mode: 'none', container: stopped, native: { installed: true, path: 'C:/o.exe', running: false } }),
    )
    expect(c.actions).toEqual([{ kind: 'ollama-start', label: 'Iniciar o Ollama local' }])
  })

  it('nada no Windows: instalar e usar o local', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env({
        apiUp: false,
        mode: 'none',
        gpu: { vendor: 'amd', name: null },
        docker: { installed: false, running: false },
        container: stopped,
        recommendation: { mode: 'native', reason: 'x' },
      }),
    )
    expect(c.actions).toEqual([{ kind: 'ollama-use-native', label: 'Instalar e usar o Ollama local' }])
  })

  it('nada no macOS: sem ação, com link de download', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env({
        platform: 'darwin',
        apiUp: false,
        mode: 'none',
        canInstallNative: false,
        docker: { installed: false, running: false },
        container: stopped,
        recommendation: { mode: 'native', reason: 'x' },
      }),
    )
    expect(c.actions).toEqual([])
    expect(c.help).toContain('https://ollama.com/download')
    assertNoEmDash(c)
  })

  it('Docker instalado mas parado, sem nativo: ajuda para abrir o Docker Desktop, com a ação local', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env({
        apiUp: false,
        mode: 'none',
        docker: { installed: true, running: false },
        container: stopped,
        gpu: { vendor: 'amd', name: null },
        recommendation: { mode: 'native', reason: 'x' },
      }),
    )
    expect(c.help).toBe('Abra o Docker Desktop e aguarde ele iniciar.')
    expect(kinds(c)).toEqual(['ollama-use-native'])
  })

  it('recomendação Docker com Docker instalado e sem container: usar o Docker', async () => {
    const c = await checkOllama(baseDeps(), snap1, env({ apiUp: false, mode: 'none', container: stopped }))
    expect(c.actions).toEqual([{ kind: 'ollama-use-docker', label: 'Usar o Ollama no Docker' }])
  })

  it('conflict: warn com a ação recomendada', async () => {
    const c = await checkOllama(baseDeps(), snap1, env({ mode: 'conflict', recommendation: { mode: 'native', reason: 'r' } }))
    expect(c.state).toBe('warn')
    expect(c.title).toBe('Ollama')
    expect(c.summary).toBe('O Ollama está rodando no Docker e no computador ao mesmo tempo. Os dois disputam a mesma porta.')
    expect(kinds(c)).toEqual(['ollama-use-native'])
    const d = await checkOllama(baseDeps(), snap1, env({ mode: 'conflict' }))
    expect(kinds(d)).toEqual(['ollama-use-docker'])
    assertNoEmDash(c)
  })

  it('ok em Docker sem consultar o docker de novo, com título Docker', async () => {
    const exec = async () => {
      throw new Error('não deve chamar docker')
    }
    const c = await checkOllama(baseDeps({ exec }), snap1, env(), bench())
    expect(c.state).toBe('ok')
    expect(c.stateLabel).toBe('Conectado')
    expect(c.title).toBe('Ollama (Docker)')
    expect(c.summary).toBe('Rodando no Docker, com os modelos que os projetos usam.')
  })

  it('ok em local, sem container, com título local', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env({
        mode: 'native',
        container: stopped,
        native: { installed: true, path: 'p', running: true },
        recommendation: { mode: 'native', reason: 'r' },
      }),
      bench(),
    )
    expect(c.state).toBe('ok')
    expect(c.title).toBe('Ollama (local)')
    expect(c.summary).toBe('Rodando no computador (local), com os modelos que os projetos usam.')
    expect(c.facts[0]).toEqual({ label: 'Modo', value: 'Local' })
  })

  it('warn por modelo faltando, com ollama-pull', async () => {
    const c = await checkOllama(baseDeps(), snap1, env({ models: [] }), bench())
    expect(c.state).toBe('warn')
    expect(c.actions[0]).toEqual({ kind: 'ollama-pull', label: 'Baixar nomic-embed-text', model: 'nomic-embed-text' })
  })

  it('facts na ordem, com benchmark', async () => {
    const c = await checkOllama(baseDeps(), snap1, env(), bench())
    expect(c.facts).toEqual([
      { label: 'Modo', value: 'Docker' },
      { label: 'Processador', value: 'GPU (4,0 GB de VRAM)' },
      { label: 'Velocidade', value: '42,5 chunks/s' },
      { label: 'Placa de vídeo', value: 'NVIDIA RTX 4070' },
      { label: 'Modelos instalados', value: 'nomic-embed-text:latest' },
      { label: 'Projetos que dependem', value: '1 projeto(s): p1' },
    ])
  })

  it('facts sem benchmark: ainda não medido, sem velocidade nem placa', async () => {
    const c = await checkOllama(baseDeps(), snap1, env({ gpu: { vendor: 'none', name: null } }), null)
    expect(c.facts.map((f) => f.label)).toEqual(['Modo', 'Processador', 'Modelos instalados', 'Projetos que dependem'])
    expect(c.facts[1].value).toBe('ainda não medido')
    const cpu = await checkOllama(baseDeps(), snap1, env(), bench({ processor: 'cpu', vramMB: null }))
    expect(cpu.facts[1].value).toBe('CPU')
  })

  it('benchmark que falhou não mostra velocidade', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env(),
      bench({ ok: false, chunksPerSecond: null, processor: 'unknown', error: 'x' }),
    )
    expect(c.facts.some((f) => f.label === 'Velocidade')).toBe(false)
  })

  it('troca sugerida quando o modo difere e o processador é CPU ou desconhecido', async () => {
    const e = env({ mode: 'docker', recommendation: { mode: 'native', reason: 'Use o local.' } })
    const c = await checkOllama(baseDeps(), snap1, e, bench({ processor: 'cpu', vramMB: null }))
    expect(c.actions).toContainEqual({ kind: 'ollama-use-native', label: 'Trocar para o Ollama local (usa sua GPU)' })
    expect(c.help).toBe('Use o local.')
    const u = await checkOllama(baseDeps(), snap1, e, null)
    expect(kinds(u)).toContain('ollama-use-native')
    const back = await checkOllama(
      baseDeps(),
      snap1,
      env({ mode: 'native', recommendation: { mode: 'docker', reason: 'r' } }),
      bench({ processor: 'cpu' }),
    )
    expect(back.actions).toContainEqual({ kind: 'ollama-use-docker', label: 'Trocar para o Ollama no Docker' })
    assertNoEmDash(c)
  })

  it('sem troca quando já está em GPU ou quando o modo é o recomendado', async () => {
    const gpu = await checkOllama(baseDeps(), snap1, env({ recommendation: { mode: 'native', reason: 'r' } }), bench())
    expect(kinds(gpu)).toEqual(['ollama-benchmark', 'ollama-stop'])
    expect(gpu.help).toBeNull()
    const same = await checkOllama(baseDeps(), snap1, env(), bench({ processor: 'cpu' }))
    expect(kinds(same)).toEqual(['ollama-benchmark', 'ollama-stop'])
  })

  it('ações secundárias de medir e parar', async () => {
    const c = await checkOllama(baseDeps(), snap1, env(), bench())
    expect(c.actions).toEqual([
      { kind: 'ollama-benchmark', label: 'Medir velocidade', secondary: true },
      { kind: 'ollama-stop', label: 'Parar o Ollama', secondary: true },
    ])
    assertNoEmDash(c)
  })

  it('env null mantém o caminho antigo (docker ps)', async () => {
    let called = false
    const exec = async () => {
      called = true
      return { code: 0, stdout: '', stderr: '' }
    }
    const c = await checkOllama(baseDeps({ exec }), snap1, null, null)
    expect(called).toBe(true)
    expect(c.title).toBe('Ollama (Docker)')
  })

  it('checkAll usa o ambiente e o título do modo', async () => {
    const checks = await checkAll(baseDeps(), snap1, env({ mode: 'native' }), bench())
    expect(checks.find((x) => x.id === 'ollama')?.title).toBe('Ollama (local)')
  })

  it('conflict com a API no ar mostra os modelos instalados; API fora, sem dados', async () => {
    const up = await checkOllama(baseDeps(), snap1, env({ mode: 'conflict', models: ['a:latest', 'b'] }))
    expect(up.facts).toContainEqual({ label: 'Modelos instalados', value: 'a:latest, b' })
    const none = await checkOllama(baseDeps(), snap1, env({ mode: 'conflict', models: [] }))
    expect(none.facts).toContainEqual({ label: 'Modelos instalados', value: 'nenhum' })
    const down = await checkOllama(baseDeps(), snap1, env({ mode: 'conflict', apiUp: false, models: [] }))
    expect(down.facts).toContainEqual({ label: 'Modelos instalados', value: 'sem dados' })
  })

  it('modo none com a API no ar (processo não detectado) conta como local, sem sugerir trocar para o local', async () => {
    const c = await checkOllama(
      baseDeps(),
      snap1,
      env({ mode: 'none', container: stopped, recommendation: { mode: 'native', reason: 'r' } }),
      bench({ processor: 'cpu', vramMB: null }),
    )
    expect(c.state).toBe('ok')
    expect(c.title).toBe('Ollama (local)')
    expect(c.facts[0]).toEqual({ label: 'Modo', value: 'Local' })
    expect(kinds(c)).not.toContain('ollama-use-native')
    const checks = await checkAll(baseDeps(), snap1, env({ mode: 'none', container: stopped }), null)
    expect(checks.find((x) => x.id === 'ollama')?.title).toBe('Ollama (local)')
  })
})

describe('checkOllama - botão Iniciar diz o que a tarefa liga (chooseStartMode)', () => {
  const both = (rec: 'docker' | 'native'): OllamaEnvironment =>
    env({
      apiUp: false,
      mode: 'none',
      container: { exists: true, running: false },
      native: { installed: true, path: 'C:/o.exe', running: false },
      recommendation: { mode: rec, reason: 'r' },
    })

  it('preferido nativo com container existente: Iniciar o Ollama local', async () => {
    const c = await checkOllama(baseDeps(), snap1, both('docker'), null, 'native')
    expect(c.actions).toEqual([{ kind: 'ollama-start', label: 'Iniciar o Ollama local' }])
  })

  it('preferido docker com nativo recomendado: Iniciar container', async () => {
    const c = await checkOllama(baseDeps(), snap1, both('native'), null, 'docker')
    expect(c.actions).toEqual([{ kind: 'ollama-start', label: 'Iniciar container' }])
  })

  it('sem preferência: segue a recomendação (antes, o container vencia sempre)', async () => {
    const c = await checkOllama(baseDeps(), snap1, both('native'), null, null)
    expect(c.actions).toEqual([{ kind: 'ollama-start', label: 'Iniciar o Ollama local' }])
  })

  it('o rótulo bate com o label e os passos do catálogo para as mesmas entradas', async () => {
    const cases: Array<[OllamaEnvironment, 'docker' | 'native' | null]> = [
      [both('docker'), 'native'],
      [both('native'), 'docker'],
      [both('native'), null],
      [both('docker'), null],
    ]
    for (const [e, pref] of cases) {
      const c = await checkOllama(baseDeps(), snap1, e, null, pref)
      const job = resolveJob(
        { kind: 'ollama-start' },
        { projectById: () => undefined, folderByToken: () => undefined, ollamaEnv: () => e, preferredOllamaMode: () => pref },
      )
      const runsDocker = job.steps.some((st) => st.cmd === 'docker')
      expect(c.actions[0].label).toBe(runsDocker ? 'Iniciar container' : 'Iniciar o Ollama local')
    }
  })

  it('checkAll repassa o modo preferido', async () => {
    const checks = await checkAll(baseDeps(), snap1, both('docker'), null, 'native')
    expect(checks.find((x) => x.id === 'ollama')?.actions).toEqual([
      { kind: 'ollama-start', label: 'Iniciar o Ollama local' },
    ])
  })
})

describe('checkOllama - sem sugerir a troca que o usuário já recusou', () => {
  it('preferido igual ao modo atual: nenhuma sugestão de troca, mesmo em CPU', async () => {
    const e = env({ mode: 'docker', recommendation: { mode: 'native', reason: 'Use o local.' } })
    const c = await checkOllama(baseDeps(), snap1, e, bench({ processor: 'cpu', vramMB: null }), 'docker')
    expect(kinds(c)).toEqual(['ollama-benchmark', 'ollama-stop'])
    expect(c.help).toBeNull()
  })

  it('preferido diferente do modo atual (ou nenhum): a sugestão continua', async () => {
    const e = env({ mode: 'docker', recommendation: { mode: 'native', reason: 'Use o local.' } })
    const other = await checkOllama(baseDeps(), snap1, e, bench({ processor: 'cpu', vramMB: null }), 'native')
    expect(kinds(other)).toContain('ollama-use-native')
    const none = await checkOllama(baseDeps(), snap1, e, bench({ processor: 'cpu', vramMB: null }), null)
    expect(kinds(none)).toContain('ollama-use-native')
  })
})

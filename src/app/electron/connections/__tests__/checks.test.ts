import { describe, expect, it } from 'vitest'
import { checkAll, checkClaude, checkOllama, checkRagx, type CheckDeps } from '../checks'
import type { ConnectionCheck, ProjectSnapshot, Snapshot } from '../../../src/types/ragx-bridge'

function project(over: Partial<ProjectSnapshot> = {}): ProjectSnapshot {
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
    ...over,
  }
}

function snapshot(projects: ProjectSnapshot[]): Snapshot {
  return { projects, generatedAt: '2026-09-23T10:00:00Z' }
}

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

/** Todo texto visível do painel: nenhum travessão (—), regra global do painel. */
function assertNoEmDash(check: ConnectionCheck): void {
  expect(check.summary).not.toContain('—')
  expect(check.stateLabel).not.toContain('—')
  if (check.help !== null) expect(check.help).not.toContain('—')
  for (const fact of check.facts) {
    expect(fact.label).not.toContain('—')
    expect(fact.value).not.toContain('—')
  }
  for (const action of check.actions) {
    expect(action.label).not.toContain('—')
  }
}

describe('checkRagx', () => {
  it('resolveRagx() null vira error com instrução de instalação', async () => {
    const check = await checkRagx(baseDeps({ resolveRagx: () => null }))
    expect(check.id).toBe('ragx')
    expect(check.title).toBe('RAGX CLI')
    expect(check.state).toBe('error')
    expect(check.stateLabel).toBe('Não conectado')
    expect(check.summary).toBe('O comando ragx não foi encontrado nesta máquina.')
    expect(check.help).toBe(
      'Instale com o instalador do RAGX (install.ps1 no Windows, install.sh no Linux e macOS) e reabra o painel.',
    )
    expect(check.actions).toEqual([])
    expect(check.lastMcpCallAt).toBeNull()
    assertNoEmDash(check)
  })

  it('exec --version com code 0 vira ok com versão e local', async () => {
    const check = await checkRagx(
      baseDeps({
        resolveRagx: () => 'C:/tools/ragx.exe',
        exec: async (file, args) => {
          expect(file).toBe('C:/tools/ragx.exe')
          expect(args).toEqual(['--version'])
          return { code: 0, stdout: 'ragx 1.2.3\n', stderr: '' }
        },
      }),
    )
    expect(check.state).toBe('ok')
    expect(check.stateLabel).toBe('Conectado')
    expect(check.summary).toBe('Respondendo normalmente.')
    expect(check.facts).toEqual([
      { label: 'Versão', value: 'ragx 1.2.3' },
      { label: 'Local', value: 'C:/tools/ragx.exe' },
    ])
    expect(check.help).toBeNull()
    assertNoEmDash(check)
  })

  it('exec --version com code != 0 vira error com local e 3 primeiras linhas do stderr em help', async () => {
    const check = await checkRagx(
      baseDeps({
        exec: async () => ({
          code: 1,
          stdout: '',
          stderr: 'linha 1\nlinha 2\nlinha 3\nlinha 4 nunca aparece',
        }),
      }),
    )
    expect(check.state).toBe('error')
    expect(check.summary).toBe('O ragx foi encontrado mas não respondeu.')
    expect(check.facts).toEqual([{ label: 'Local', value: 'C:/tools/ragx.exe' }])
    expect(check.help).toBe('linha 1\nlinha 2\nlinha 3')
    assertNoEmDash(check)
  })

  it('exceção inesperada nunca escapa: vira error com o motivo no summary', async () => {
    const check = await checkRagx(
      baseDeps({
        resolveRagx: () => {
          throw new Error('boom')
        },
      }),
    )
    expect(check.state).toBe('error')
    expect(check.summary).toContain('boom')
    expect(check.lastMcpCallAt).toBeNull()
  })
})

describe('checkClaude', () => {
  it('~/.claude.json ausente vira error com ação de registro', async () => {
    const check = await checkClaude(baseDeps({ readFile: () => null }), null)
    expect(check.id).toBe('claude')
    expect(check.title).toBe('Claude Code')
    expect(check.state).toBe('error')
    expect(check.summary).toBe('O Claude Code ainda não foi usado nesta conta (sem ~/.claude.json).')
    expect(check.actions).toEqual([{ kind: 'mcp-register', label: 'Registrar no Claude Code' }])
    expect(check.lastMcpCallAt).toBeNull()
    assertNoEmDash(check)
  })

  it('JSON inválido vira error sem ação', async () => {
    const check = await checkClaude(baseDeps({ readFile: () => '{ nao é json' }), null)
    expect(check.state).toBe('error')
    expect(check.summary).toBe('Não foi possível ler ~/.claude.json.')
    expect(check.actions).toEqual([])
    assertNoEmDash(check)
  })

  it('mcpServers.ragx com command absoluto que não existe mais vira warn', async () => {
    const raw = JSON.stringify({ mcpServers: { ragx: { command: 'C:/tools/ragx.exe' } } })
    const check = await checkClaude(baseDeps({ readFile: () => raw, exists: () => false }), null)
    expect(check.state).toBe('warn')
    expect(check.stateLabel).toBe('Atenção')
    expect(check.summary).toBe('O RAGX está registrado, mas o comando gravado não existe mais.')
    expect(check.actions).toEqual([{ kind: 'mcp-register', label: 'Registrar de novo' }])
    assertNoEmDash(check)
  })

  it('mcpServers.ragx com command relativo (ex.: "ragx") vira ok mesmo sem checar disco', async () => {
    const raw = JSON.stringify({ mcpServers: { ragx: { command: 'ragx' } } })
    const check = await checkClaude(
      baseDeps({
        readFile: () => raw,
        exists: () => {
          throw new Error('não deveria checar disco pra comando relativo')
        },
      }),
      null,
    )
    expect(check.state).toBe('ok')
    expect(check.summary).toBe('O RAGX está registrado para todos os projetos.')
    expect(check.actions).toEqual([])
    assertNoEmDash(check)
  })

  it('mcpServers.ragx com command absoluto existente vira ok', async () => {
    const raw = JSON.stringify({ mcpServers: { ragx: { command: 'C:/tools/ragx.exe' } } })
    const check = await checkClaude(baseDeps({ readFile: () => raw, exists: () => true }), null)
    expect(check.state).toBe('ok')
    expect(check.summary).toBe('O RAGX está registrado para todos os projetos.')
  })

  it('caso real desta máquina: sem mcpServers.ragx no topo, só em projects[...].mcpServers.ragx de 1 projeto', async () => {
    const raw = JSON.stringify({
      projects: {
        'C:/projects/aivonlabs/ragx': { mcpServers: { ragx: { command: 'ragx' } } },
        'C:/projects/aivonlabs/outro': {},
      },
    })
    const check = await checkClaude(baseDeps({ readFile: () => raw }), null)
    expect(check.state).toBe('warn')
    expect(check.summary).toBe(
      'O RAGX está registrado só em 1 projeto(s). Nos outros o Claude Code não enxerga o índice.',
    )
    expect(check.actions).toEqual([{ kind: 'mcp-register', label: 'Registrar para todos os projetos' }])
    expect(check.facts).toEqual([{ label: 'Projetos', value: 'ragx' }])
    assertNoEmDash(check)
  })

  it('lista até 5 projetos nos facts quando registrado localmente em mais de 5', async () => {
    const projects: Record<string, { mcpServers?: { ragx: { command: string } } }> = {}
    for (let i = 1; i <= 7; i++) {
      projects[`C:/projects/p${i}`] = { mcpServers: { ragx: { command: 'ragx' } } }
    }
    const raw = JSON.stringify({ projects })
    const check = await checkClaude(baseDeps({ readFile: () => raw }), null)
    expect(check.summary).toBe(
      'O RAGX está registrado só em 7 projeto(s). Nos outros o Claude Code não enxerga o índice.',
    )
    expect(check.facts[0].value.split(', ')).toHaveLength(5)
  })

  it('nenhum registro (nem topo nem local) vira error "não está registrado"', async () => {
    const raw = JSON.stringify({ projects: { 'C:/p1': {} } })
    const check = await checkClaude(baseDeps({ readFile: () => raw }), null)
    expect(check.state).toBe('error')
    expect(check.summary).toBe('O RAGX não está registrado no Claude Code.')
    expect(check.actions).toEqual([{ kind: 'mcp-register', label: 'Registrar no Claude Code' }])
    assertNoEmDash(check)
  })

  it('lastMcpCallAt é o maior telemetry.lastCallAt entre os projetos do snapshot', async () => {
    const raw = JSON.stringify({ mcpServers: { ragx: { command: 'ragx' } } })
    const snap = snapshot([
      project({ id: 'a', telemetry: { callsByTool: [], totalCalls: 1, tokensDelivered: 1, lastCallAt: '2026-09-20T10:00:00Z' } }),
      project({ id: 'b', telemetry: { callsByTool: [], totalCalls: 1, tokensDelivered: 1, lastCallAt: '2026-09-22T10:00:00Z' } }),
      project({ id: 'c', telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null } }),
    ])
    const check = await checkClaude(baseDeps({ readFile: () => raw }), snap)
    expect(check.lastMcpCallAt).toBe('2026-09-22T10:00:00Z')
  })

  it('lastMcpCallAt é null quando não há snapshot ou nenhum projeto chamou o MCP', async () => {
    const raw = JSON.stringify({ mcpServers: { ragx: { command: 'ragx' } } })
    const semSnapshot = await checkClaude(baseDeps({ readFile: () => raw }), null)
    expect(semSnapshot.lastMcpCallAt).toBeNull()

    const snapshotSemChamadas = snapshot([project({ telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null } })])
    const check = await checkClaude(baseDeps({ readFile: () => raw }), snapshotSemChamadas)
    expect(check.lastMcpCallAt).toBeNull()
  })

  it('exceção inesperada (readFile lançando) nunca escapa: vira error', async () => {
    const check = await checkClaude(
      baseDeps({
        readFile: () => {
          throw new Error('disco falhou')
        },
      }),
      null,
    )
    expect(check.state).toBe('error')
    expect(check.summary).toContain('disco falhou')
  })
})

describe('checkOllama', () => {
  const dockerOk: Partial<CheckDeps> = {
    exec: async () => ({ code: 0, stdout: 'running\n', stderr: '' }),
    httpGetJson: async () => ({ models: [{ name: 'nomic-embed-text:latest' }] }),
  }

  it('docker ps com código != 0 vira error "Docker não está rodando"', async () => {
    const check = await checkOllama(baseDeps({ exec: async () => ({ code: 1, stdout: '', stderr: 'falhou' }) }), null)
    expect(check.id).toBe('ollama')
    expect(check.title).toBe('Ollama (Docker)')
    expect(check.state).toBe('error')
    expect(check.summary).toBe('O Docker não está rodando.')
    expect(check.help).toBe('Abra o Docker Desktop e aguarde ele iniciar.')
    expect(check.lastMcpCallAt).toBeNull()
    assertNoEmDash(check)
  })

  it('saída vazia do docker ps vira error "Não existe um container chamado ollama"', async () => {
    const check = await checkOllama(baseDeps({ exec: async () => ({ code: 0, stdout: '', stderr: '' }) }), null)
    expect(check.state).toBe('error')
    expect(check.summary).toBe('Não existe um container chamado ollama.')
    expect(check.help).toBe('Crie com: docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama')
    assertNoEmDash(check)
  })

  it('container em estado diferente de running vira error com ação ollama-start', async () => {
    const check = await checkOllama(baseDeps({ exec: async () => ({ code: 0, stdout: 'exited\n', stderr: '' }) }), null)
    expect(check.state).toBe('error')
    expect(check.summary).toBe('O container ollama está parado.')
    expect(check.actions).toEqual([{ kind: 'ollama-start', label: 'Iniciar container' }])
    assertNoEmDash(check)
  })

  it('httpGetJson null (API não responde) vira error sem ação', async () => {
    const check = await checkOllama(
      baseDeps({ exec: async () => ({ code: 0, stdout: 'running\n', stderr: '' }), httpGetJson: async () => null }),
      null,
    )
    expect(check.state).toBe('error')
    expect(check.summary).toBe('O container está rodando mas a API não responde na porta 11434.')
    expect(check.actions).toEqual([])
    assertNoEmDash(check)
  })

  it('modelo faltando vira warn com uma ação ollama-pull por modelo', async () => {
    const snap = snapshot([
      project({ id: 'p1', embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' }),
      project({ id: 'p2', embeddingModel: 'mxbai-embed-large', embeddingProvider: 'ollama' }),
    ])
    const check = await checkOllama(
      baseDeps({ ...dockerOk, httpGetJson: async () => ({ models: [{ name: 'nomic-embed-text:latest' }] }) }),
      snap,
    )
    expect(check.state).toBe('warn')
    expect(check.stateLabel).toBe('Atenção')
    expect(check.summary).toBe('Falta baixar 1 modelo(s).')
    expect(check.actions).toEqual([{ kind: 'ollama-pull', label: 'Baixar mxbai-embed-large', model: 'mxbai-embed-large' }])
    assertNoEmDash(check)
  })

  it('todos os modelos presentes (comparando nome e nome:latest) vira ok', async () => {
    const snap = snapshot([project({ embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' })])
    const check = await checkOllama(baseDeps(dockerOk), snap)
    expect(check.state).toBe('ok')
    expect(check.stateLabel).toBe('Conectado')
    expect(check.summary).toBe('Rodando, com os modelos que os projetos usam.')
    expect(check.actions).toEqual([])
    assertNoEmDash(check)
  })

  it('sem nenhum projeto dependente vira ok sem exigir nenhum modelo', async () => {
    const check = await checkOllama(baseDeps(dockerOk), snapshot([]))
    expect(check.state).toBe('ok')
    expect(check.actions).toEqual([])
  })

  it('embeddingProvider null com modelo sem "/" conta pela heurística (projeto sem status.json)', async () => {
    const snap = snapshot([project({ embeddingModel: 'nomic-embed-text', embeddingProvider: null })])
    const check = await checkOllama(
      baseDeps({ ...dockerOk, httpGetJson: async () => ({ models: [] }) }),
      snap,
    )
    expect(check.state).toBe('warn')
    expect(check.summary).toBe('Falta baixar 1 modelo(s).')
  })

  it('embeddingProvider null com modelo contendo "/" não conta (não é heurística ollama)', async () => {
    const snap = snapshot([project({ embeddingModel: 'org/modelo-openai', embeddingProvider: null })])
    const check = await checkOllama(baseDeps({ ...dockerOk, httpGetJson: async () => ({ models: [] }) }), snap)
    expect(check.state).toBe('ok')
    expect(check.summary).toBe('Rodando, com os modelos que os projetos usam.')
  })

  it('embeddingProvider diferente de ollama e não nulo não conta', async () => {
    const snap = snapshot([project({ embeddingModel: 'text-embedding-3', embeddingProvider: 'openai' })])
    const check = await checkOllama(baseDeps({ ...dockerOk, httpGetJson: async () => ({ models: [] }) }), snap)
    expect(check.state).toBe('ok')
  })

  it('modelos duplicados entre projetos contam uma única vez (distinct)', async () => {
    const snap = snapshot([
      project({ id: 'p1', embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' }),
      project({ id: 'p2', embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' }),
    ])
    const check = await checkOllama(baseDeps({ ...dockerOk, httpGetJson: async () => ({ models: [] }) }), snap)
    expect(check.summary).toBe('Falta baixar 1 modelo(s).')
  })

  it('facts trazem modelos instalados e projetos que dependem (até 3 nomes)', async () => {
    const snap = snapshot([
      project({ id: 'p1', name: 'projeto-1', embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' }),
      project({ id: 'p2', name: 'projeto-2', embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama' }),
    ])
    const check = await checkOllama(baseDeps(dockerOk), snap)
    expect(check.facts).toEqual([
      { label: 'Modelos instalados', value: 'nomic-embed-text:latest' },
      { label: 'Projetos que dependem', value: '2 projeto(s): projeto-1, projeto-2' },
    ])
  })

  it('exceção inesperada (httpGetJson rejeitando) nunca escapa: vira error', async () => {
    const check = await checkOllama(
      baseDeps({
        exec: async () => ({ code: 0, stdout: 'running\n', stderr: '' }),
        httpGetJson: async () => {
          throw new Error('rede caiu')
        },
      }),
      null,
    )
    expect(check.state).toBe('error')
    expect(check.summary).toContain('rede caiu')
  })
})

describe('checkAll', () => {
  it('roda as 3 checagens e devolve na ordem ragx, claude, ollama', async () => {
    const checks = await checkAll(baseDeps(), null)
    expect(checks.map((c) => c.id)).toEqual(['ragx', 'claude', 'ollama'])
  })
})

/*
 * `window.ragx` simulado para o harness visual (RAGX-0181). Roda no navegador, antes da página, por `addInitScript`.
 * ~12 projetos nas formas de `src/test/snap.ts`; nomes e caminhos longos de propósito, porque é o texto comprido
 * que estoura o layout. Tudo o que o painel chama existe; o que não importa para o layout devolve vazio.
 */
(() => {
  const now = Date.now()
  const iso = (msAgo) => new Date(now - msAgo).toISOString()
  const MIN = 60_000

  const NAMES = [
    'juriflux', 'aivon-landing-page', 'orkestria-backend-com-nome-muito-comprido-para-testar-quebra',
    'ragx', 'clientes-sp', 'embedder', 'sem-hooks', 'quebrado', 'sumido', 'ocupado', 'api-gateway', 'docs-site',
  ]

  const projects = NAMES.map((name, i) => {
    const missing = name === 'sumido'
    const noIndex = name === 'embedder'
    return {
      id: name,
      name,
      path: missing ? 'C:/projects/clientes/pasta-que-sumiu/' + name : `C:/Users/pessoa/projects/aivonlabs/cliente-${i}/${name}`,
      exists: !missing,
      embeddingModel: 'nomic-embed-text',
      embeddingProvider: 'ollama',
      visibility: 'workspace',
      counts: missing ? null : { documents: 120 + i * 37, chunks: 900 + i * 410, embeddings: noIndex ? 300 : 900 + i * 410, pendingEmbeddings: noIndex ? 1200 : 0 },
      countsUnavailableReason: missing ? 'pasta do projeto não existe mais' : null,
      index: missing ? null : { finishedAt: iso((i + 1) * 17 * MIN), mode: 'incremental', source: i % 3 === 0 ? 'hook:post-commit' : 'cli', branch: 'main', commit: 'c1' },
      git: missing ? null : { branch: name === 'ragx' ? 'feat/uma-branch-com-nome-bem-comprido-para-quebrar-linha' : 'main', commit: i === 4 ? 'c2' : 'c1' },
      hooksInstalled: name !== 'sem-hooks',
      running: name === 'ocupado' ? { source: 'cli', startedAt: iso(2 * MIN) } : null,
      pending: false,
      lastError: name === 'quebrado' ? 'embedder fora do ar' : null,
      hasStatusFile: true,
      telemetry: {
        callsByTool: [
          { tool: 'build_context', count: 40 + i * 3 },
          { tool: 'search_hybrid', count: 22 + i },
          { tool: 'get_chunk', count: 9 },
        ],
        totalCalls: 71 + i * 4,
        tokensDelivered: 120_000 + i * 5000,
        lastCallAt: iso(i * 9 * MIN),
        savings: savingsFor(i),
      },
    }
  })

  function savingsFor(i) {
    const days = Array.from({ length: 14 }, (_, d) => {
        const day = new Date(now - (13 - d) * 86_400_000)
        return {
          date: `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`,
          baseline: 90_000 + d * 4000,
          delivered: 12_000 + d * 700,
          calls: 10 + d,
        }
    })
    return {
      days,
      baseline: days.reduce((n, x) => n + x.baseline, 0),
      delivered: days.reduce((n, x) => n + x.delivered, 0),
      calls: days.reduce((n, x) => n + x.calls, 0),
    }
  }

  const connections = [
    {
      id: 'ragx', title: 'RAGX CLI', state: 'ok', stateLabel: 'Conectado', summary: 'Respondendo normalmente.',
      facts: [{ label: 'Versão', value: 'ragx 1.0.0b5' }, { label: 'Local', value: 'C:/Users/pessoa/AppData/Local/Programs/ragx/bin/ragx.exe' }],
      actions: [], help: null, lastMcpCallAt: null,
    },
    {
      id: 'claude', title: 'Claude Code', state: 'warn', stateLabel: 'Atenção',
      summary: 'O RAGX está registrado só em 1 projeto(s). Nos outros o Claude Code não enxerga o índice.',
      facts: [{ label: 'Projetos', value: 'ragx' }],
      actions: [{ kind: 'mcp-register', label: 'Registrar para todos os projetos' }],
      help: 'claude mcp add ragx -- ragx mcp serve', lastMcpCallAt: iso(5 * MIN),
    },
    {
      id: 'ollama', title: 'Ollama (Docker)', state: 'warn', stateLabel: 'Atenção', summary: 'Falta baixar 1 modelo(s).',
      facts: [{ label: 'Modelos instalados', value: 'nenhum' }, { label: 'Projetos que dependem', value: '12 projeto(s): juriflux, aivon-landing-page, ragx e outros' }],
      actions: [{ kind: 'ollama-pull', label: 'Baixar nomic-embed-text', model: 'nomic-embed-text' }, { kind: 'ollama-benchmark', label: 'Medir velocidade', secondary: true }],
      help: null, lastMcpCallAt: null,
    },
  ]

  const job = (over) => ({
    id: 'j1', kind: 'embed', label: 'Gerar embeddings em juriflux', projectId: 'juriflux', model: null, state: 'running',
    step: 1, steps: 1, phase: 'embed', done: 400, total: 1000, etaSeconds: 120, ratePerSecond: 12,
    note: null, error: null, logTail: [], queuedAt: iso(3 * MIN), startedAt: iso(2 * MIN), finishedAt: null, ...over,
  })
  const jobs = [
    job(),
    job({ id: 'j2', label: 'Atualizar ragx', projectId: 'ragx', kind: 'update', state: 'queued', done: null, total: null, startedAt: null }),
    job({ id: 'j3', label: 'Reindexar do zero em quebrado', projectId: 'quebrado', kind: 'reindex-full', state: 'failed', error: 'o embedder não respondeu em 30 s', finishedAt: iso(MIN) }),
  ]

  const kinds = ['mcp', 'cli', 'session']
  const activity = Array.from({ length: 40 }, (_, i) => {
    const kind = kinds[i % 3]
    const p = projects[i % projects.length]
    return {
      id: `e${i}`, ts: iso(i * 40_000), projectId: p.id, projectName: p.name, kind,
      name: kind === 'mcp' ? 'build_context' : kind === 'cli' ? 'search' : 'session_start',
      ms: 80 + i * 13, ok: i % 11 !== 0, tokensDelivered: kind === 'mcp' ? 1800 : null, baselineTokens: kind === 'mcp' ? 24000 : null,
      errCode: i % 11 === 0 ? 'not_found' : null, respChars: 4200, respTokens: 1100,
      client: 'claude-code', profile: i % 2 ? 'empresa' : 'padrão', session: 'deadbeef',
    }
  })

  const status = (project) => ({
    initialized: true, documents: 300, chunks: 2400, embeddings: 2400,
    freshness: { state: project === 'ragx' ? 'stale' : 'fresh', current: { branch: 'main', commit: 'c1', dirty: false }, reasons: project === 'ragx' ? [{ kind: 'commit', text: 'o HEAD mudou desde a última indexação' }] : [] },
    recent_runs: [],
  })
  const run = (i) => ({
    id: i + 1, started_at: iso((i + 1) * 40 * MIN), finished_at: iso((i + 1) * 40 * MIN - 30_000), mode: i % 2 ? 'incremental' : 'full', source: 'cli',
    git_branch: 'main', git_commit: 'abc1234def5678', git_dirty: 0, indexed: 12 + i, error: null,
  })

  const none = () => () => {}
  const claude = {
    enabled: true,
    profiles: [
      { id: 'claude-code', name: 'padrão', label: 'Claude Code', dir: 'C:/Users/pessoa/.claude', enabled: true, hint: true, added: false },
      { id: 'claude-code:empresa', name: 'empresa', label: 'Claude Code (empresa)', dir: 'C:/Users/pessoa/.claude-empresa-com-um-nome-comprido', enabled: false, hint: false, added: true },
    ],
  }

  window.__VISUAL_ONBOARDING__ = new URLSearchParams(location.search).get('onboarding') === '1'
  window.ragx = {
    // `?snapshotDelay=3000` atrasa a primeira resposta (medição de primeira pintura, RAGX-0182)
    getSnapshot: async () => {
      const delay = Number(new URLSearchParams(location.search).get('snapshotDelay') || 0)
      if (delay > 0) await new Promise((r) => setTimeout(r, delay))
      return { projects, generatedAt: new Date().toISOString(), connectionsHealth: 'warn' }
    },
    onSnapshot: none,
    getActivity: async () => activity,
    onActivity: none,
    getProjectStatus: async (id) => status(id),
    runTrial: async () => ({ cases: 8, totals: { baseline_tokens: 90000, ragx_tokens: 9000, saved_ratio: 0.9, source_coverage: 0.95 } }),
    getIndexRuns: async (id, offset) => ({ runs: Array.from({ length: 8 }, (_, i) => run(offset + i)), total: 20 }),
    runSecurityScan: async () => ({ root: 'C:/x', scanned: 300, blocked: [], redacted: [], skipped: 0, ruleset: { version: '1', rules: 60, disabled: [] }, policy: 'redact' }),
    getConnections: async () => connections,
    onConnections: none,
    listJobs: async () => jobs,
    onJobs: none,
    enqueueJob: async () => job({ state: 'queued' }),
    cancelJob: async () => true,
    pickFolder: async () => null,
    discover: async () => ({ items: [], truncated: false }),
    getSettings: async () => {
      const theme = localStorage.getItem('ragx.theme')
      return { onboardingDone: !window.__VISUAL_ONBOARDING__, ...(theme === 'light' || theme === 'system' ? { theme } : {}) }
    },
    setOnboardingDone: async () => {},
    setPricing: async () => {},
    setPreference: async () => {},
    setTheme: async () => {},
    getUpdateState: async () => ({ status: 'idle', currentVersion: '1.0.0-beta.5', version: null, progress: null, error: null }),
    getAutoSetup: async () => ({ enabled: true, running: false, lastRunAt: new Date(Date.now() - 4 * 60000).toISOString(), claude: { checked: 2, installed: ['empresa: aviso de edição, lembrete de busca'], error: null }, git: { queued: ['aivon-landing-page'], failed: [] } }),
    runAutoSetup: async () => ({ enabled: true, running: false, lastRunAt: new Date().toISOString(), claude: { checked: 2, installed: [], error: null }, git: { queued: [], failed: [] } }),
    onAutoSetup: () => () => {},
    checkForUpdates: async () => ({ status: 'idle', currentVersion: '1.0.0-beta.5', version: null, progress: null, error: null }),
    downloadUpdate: async () => ({ status: 'idle', currentVersion: '1.0.0-beta.5', version: null, progress: null, error: null }),
    installUpdate: async () => {},
    onUpdate: none,
    onOpenPreferences: () => () => {},
    onOpenProject: none,
    previewContext: async () => ({ intent: 'implementar', estimatedTokens: 1200, budget: 3000, fragments: [{ project: 'p', documentPath: 'src/pedido.py', lines: [10, 30], symbol: 'criar_pedido', headingPath: null, score: 0.9, tokens: 400, compressed: false, strategy: 'full', reason: 'semantico' }], dropped: [{ why: 'orcamento', count: 3 }] }),
    getAdoption: async () => ({ since: new Date(now - 6 * 86_400_000).toISOString(), sessions: 38, withCalls: 3, withoutCalls: 35, unidentified: 4, callsWithoutStart: 1, byProject: projects.slice(0, 4).map((p, i) => ({ projectId: p.id, projectName: p.name, sessions: 10 - i, withCalls: i })) }),
    runOllamaBenchmark: async () => ({ ok: true, chunksPerSecond: 40, processor: 'gpu', vramMB: 4000, model: 'nomic-embed-text', measuredAt: new Date().toISOString(), error: null }),
    getClaudeIntegration: async () => claude,
    setClaudeIntegration: async () => claude,
    setClaudeProfile: async () => claude,
    addClaudeProfile: async () => claude,
    removeClaudeProfile: async () => claude,
  }
})()

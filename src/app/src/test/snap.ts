import { vi } from 'vitest'
import type { ConnectionCheck, JobView, ProjectSnapshot, RagxBridge } from '../types/ragx-bridge'

/** Projeto "Atualizado" por padrão; cada teste troca só o que importa. */
export function snap(over: Partial<ProjectSnapshot> = {}): ProjectSnapshot {
  return {
    id: 'p1', name: 'p1', path: 'C:/p1', exists: true,
    embeddingModel: 'nomic-embed-text', embeddingProvider: 'ollama', visibility: 'workspace',
    counts: { documents: 3, chunks: 10, embeddings: 10, pendingEmbeddings: 0 },
    countsUnavailableReason: null,
    index: { finishedAt: '2026-09-23T10:00:00Z', mode: 'incremental', source: 'cli', branch: 'main', commit: 'c1' },
    git: { branch: 'main', commit: 'c1' },
    hooksInstalled: true, running: null, pending: false, lastError: null, hasStatusFile: true,
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null },
    ...over,
  }
}

/** Tarefa rodando por padrão. */
export function job(over: Partial<JobView> = {}): JobView {
  return {
    id: 'j1', kind: 'embed', label: 'Gerar embeddings em p1', projectId: 'p1', model: null, state: 'running',
    step: 1, steps: 1, phase: 'embed', done: 40, total: 100, etaSeconds: 120, ratePerSecond: 2,
    note: null, error: null, logTail: [],
    queuedAt: '2026-09-23T10:00:00Z', startedAt: '2026-09-23T10:00:01Z', finishedAt: null,
    ...over,
  }
}

/** `window.ragx` falso, com `vi.fn()` em tudo; `over` troca o que o teste precisa. */
export function installBridge(over: Partial<RagxBridge> = {}): RagxBridge {
  const b: RagxBridge = {
    getSnapshot: vi.fn().mockResolvedValue({ projects: [], generatedAt: '2026-09-23T10:00:00Z' }),
    onSnapshot: vi.fn(() => () => {}),
    getActivity: vi.fn().mockResolvedValue([]),
    getAdoption: vi.fn().mockResolvedValue({ since: null, sessions: 0, withCalls: 0, withoutCalls: 0, unidentified: 0, callsWithoutStart: 0, byProject: [] }),
    onActivity: vi.fn(() => () => {}),
    getProjectStatus: vi.fn(),
    runTrial: vi.fn(),
    getIndexRuns: vi.fn(),
    runSecurityScan: vi.fn(),
    getConnections: vi.fn().mockResolvedValue([]),
    onConnections: vi.fn(() => () => {}),
    listJobs: vi.fn().mockResolvedValue([]),
    onJobs: vi.fn(() => () => {}),
    enqueueJob: vi.fn().mockImplementation((req) => Promise.resolve(job({ kind: req.kind, state: 'queued' }))),
    cancelJob: vi.fn().mockResolvedValue(true),
    pickFolder: vi.fn().mockResolvedValue(null),
    discover: vi.fn().mockResolvedValue({ items: [], truncated: false }),
    getSettings: vi.fn().mockResolvedValue({ onboardingDone: true }),
    setOnboardingDone: vi.fn().mockResolvedValue(undefined),
    setPricing: vi.fn().mockResolvedValue(undefined),
    setPreference: vi.fn().mockResolvedValue(undefined),
    onOpenPreferences: vi.fn(() => () => {}),
    onOpenProject: vi.fn(() => () => {}),
    setTheme: vi.fn().mockResolvedValue(undefined),
    getUpdateState: vi.fn().mockResolvedValue({ status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }),
    getAutoSetup: vi.fn().mockResolvedValue({ enabled: true, running: false, lastRunAt: null, claude: { checked: 0, installed: [], error: null }, git: { queued: [], failed: [] } }),
    runAutoSetup: vi.fn().mockResolvedValue({ enabled: true, running: false, lastRunAt: null, claude: { checked: 0, installed: [], error: null }, git: { queued: [], failed: [] } }),
    onAutoSetup: vi.fn(() => () => {}),
    checkForUpdates: vi.fn().mockResolvedValue({ status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }),
    downloadUpdate: vi.fn().mockResolvedValue({ status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }),
    installUpdate: vi.fn().mockResolvedValue(undefined),
    onUpdate: vi.fn(() => () => {}),
    previewContext: vi.fn(),
    runOllamaBenchmark: vi.fn(),
    getClaudeIntegration: vi.fn().mockResolvedValue({ enabled: true }),
    getMcpIntegrations: vi.fn().mockResolvedValue([
      { id: 'codex', label: 'Codex CLI', installed: true, enabled: false, config: 'C:/u/.codex/config.toml' },
      { id: 'gemini', label: 'Gemini CLI', installed: true, enabled: false, config: 'C:/u/.gemini/settings.json' },
      { id: 'cursor', label: 'Cursor', installed: false, enabled: false, config: 'C:/u/.cursor/mcp.json' },
      { id: 'windsurf', label: 'Windsurf', installed: false, enabled: false, config: 'C:/u/.codeium/windsurf/mcp_config.json' },
      { id: 'claude-desktop', label: 'Claude Desktop', installed: false, enabled: false, config: 'C:/u/claude_desktop_config.json' },
    ]),
    setMcpIntegration: vi.fn(),
    setClaudeIntegration: vi.fn().mockResolvedValue({ enabled: true }),
    setClaudeProfile: vi.fn(),
    addClaudeProfile: vi.fn(),
    removeClaudeProfile: vi.fn(),
    ...over,
  }
  window.ragx = b
  return b
}

/**
 * As três checagens como nesta máquina: RAGX ok, Claude Code registrado só
 * em um projeto (atenção) e Ollama sem o modelo (atenção). `over` troca por id.
 */
export function connectionChecks(over: Partial<Record<ConnectionCheck['id'], Partial<ConnectionCheck>>> = {}): ConnectionCheck[] {
  const base: ConnectionCheck[] = [
    {
      id: 'ragx', title: 'RAGX CLI', state: 'ok', stateLabel: 'Conectado', summary: 'Respondendo normalmente.',
      facts: [{ label: 'Versão', value: 'ragx 0.9.0' }, { label: 'Local', value: 'C:/Users/me/.local/bin/ragx.exe' }],
      actions: [], help: null, lastMcpCallAt: null,
    },
    {
      id: 'claude', title: 'Claude Code', state: 'warn', stateLabel: 'Atenção',
      summary: 'O RAGX está registrado só em 1 projeto(s). Nos outros o Claude Code não enxerga o índice.',
      facts: [{ label: 'Projetos', value: 'ragx' }],
      actions: [{ kind: 'mcp-register', label: 'Registrar para todos os projetos' }],
      help: null, lastMcpCallAt: '2026-09-23T11:55:00Z',
    },
    {
      id: 'ollama', title: 'Ollama (Docker)', state: 'warn', stateLabel: 'Atenção', summary: 'Falta baixar 1 modelo(s).',
      facts: [{ label: 'Modelos instalados', value: 'nenhum' }, { label: 'Projetos que dependem', value: '1 projeto(s): Juriflux' }],
      actions: [{ kind: 'ollama-pull', label: 'Baixar nomic-embed-text', model: 'nomic-embed-text' }],
      help: null, lastMcpCallAt: null,
    },
  ]
  return base.map((c) => ({ ...c, ...over[c.id] }))
}

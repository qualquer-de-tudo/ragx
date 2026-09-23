import { vi } from 'vitest'
import type { JobView, ProjectSnapshot, RagxBridge } from '../types/ragx-bridge'

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
    id: 'j1', kind: 'embed', label: 'Gerar embeddings em p1', projectId: 'p1', state: 'running',
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
    getProjectStatus: vi.fn(),
    runTrial: vi.fn(),
    runSecurityScan: vi.fn(),
    getConnections: vi.fn().mockResolvedValue([]),
    listJobs: vi.fn().mockResolvedValue([]),
    onJobs: vi.fn(() => () => {}),
    enqueueJob: vi.fn().mockImplementation((req) => Promise.resolve(job({ kind: req.kind, state: 'queued' }))),
    cancelJob: vi.fn().mockResolvedValue(true),
    pickFolder: vi.fn().mockResolvedValue(null),
    discover: vi.fn().mockResolvedValue({ items: [], truncated: false }),
    getSettings: vi.fn().mockResolvedValue({ onboardingDone: true }),
    setOnboardingDone: vi.fn().mockResolvedValue(undefined),
    ...over,
  }
  window.ragx = b
  return b
}

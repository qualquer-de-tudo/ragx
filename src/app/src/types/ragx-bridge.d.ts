import type { TelemetrySummary } from '../../electron/data/types'

export interface IndexInfo {
  finishedAt: string
  mode: string
  source: string
  branch: string | null
  commit: string | null
}

export interface ProjectSnapshot {
  id: string
  name: string
  path: string | null
  /** A pasta existe no disco. */
  exists: boolean
  embeddingModel: string | null
  /** Vem de `status.json`; sem ele, `null`. */
  embeddingProvider: string | null
  visibility: string
  counts: { documents: number; chunks: number; embeddings: number; pendingEmbeddings: number } | null
  countsUnavailableReason: string | null
  /** Último run útil (de `status.json`). */
  index: IndexInfo | null
  git: { branch: string | null; commit: string } | null
  hooksInstalled: boolean | null
  running: { source: string; startedAt: string } | null
  pending: boolean
  lastError: string | null
  hasStatusFile: boolean
  telemetry: TelemetrySummary
}

export interface Snapshot {
  projects: ProjectSnapshot[]
  generatedAt: string
}

export interface TrialResult {
  totals: {
    baseline_tokens: number
    ragx_tokens: number
    saved_ratio: number
    source_coverage: number
  }
}

export interface SecurityScanResult {
  root: string
  scanned: number
  blocked: Array<{ path: string; rule: string; severity: string; line: number; preview: string }>
  redacted: Array<{ path: string; findings: number }>
  skipped: number
  ruleset: { version: string; rules: number; disabled: string[] }
  policy: string
}

export type ConnectionId = 'ragx' | 'claude' | 'ollama'
export type ConnectionState = 'ok' | 'warn' | 'error'

export interface ConnectionAction {
  kind: 'mcp-register' | 'ollama-start' | 'ollama-pull'
  label: string
  model?: string
}

export interface ConnectionCheck {
  id: ConnectionId
  title: string
  state: ConnectionState
  stateLabel: string
  summary: string
  facts: Array<{ label: string; value: string }>
  actions: ConnectionAction[]
  help: string | null
  /**
   * Maior `telemetry.lastCallAt` entre os projetos do snapshot, ou `null`
   * quando não há snapshot ou nenhum projeto tem chamada registrada.
   * Só é preenchido na checagem `claude`; nas outras é sempre `null`. O
   * processo principal do Electron não formata data relativa (tsconfig
   * de build usa `rootDir: "electron"`, então `formatRelative` de
   * `src/format.ts` não é importável em runtime) - quem formata este
   * campo é o renderer.
   */
  lastMcpCallAt: string | null
}

export interface RagxBridge {
  getSnapshot: () => Promise<Snapshot>
  onSnapshot: (cb: (snapshot: Snapshot) => void) => () => void
  runTrial: (projectPath: string) => Promise<TrialResult>
  runSecurityScan: (projectPath: string) => Promise<SecurityScanResult>
}

declare global {
  interface Window {
    ragx: RagxBridge
  }
}

import type { TelemetrySummary } from '../../electron/data/types'
import type { PanelSettings } from '../../electron/settings'

export type { PanelSettings }

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
  /**
   * Pior dos três estados de `ConnectionCheck` (`checkAll`), preenchido pelo
   * processo principal a partir do último resultado em cache (Task 6,
   * decisão 3). `null`/ausente até a primeira checagem terminar - antes
   * disso não há dado nenhum, não é um "ok" otimista.
   */
  connectionsHealth?: 'ok' | 'warn' | 'error' | null
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

export type JobKind =
  | 'add-project'
  | 'update'
  | 'embed'
  | 'reindex-full'
  | 'sync'
  | 'graph'
  | 'dictionary'
  | 'hooks-install'
  | 'hooks-uninstall'
  | 'remove-from-hub'
  | 'mcp-register'
  | 'ollama-start'
  | 'ollama-pull'

export interface JobRequest {
  kind: JobKind
  /** Tarefas de projeto existente. */
  projectId?: string
  /** `add-project`: token da pasta escolhida pelo usuário (Task 6). */
  folderToken?: string
  /** `ollama-pull`. */
  model?: string
  /** `add-project`. */
  installHooks?: boolean
}

export type JobState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface JobView {
  id: string
  kind: JobKind
  /** Ex.: "Gerar embeddings em Juriflux" (tabela do catálogo). */
  label: string
  projectId: string | null
  /** Modelo do `ollama-pull` (é o que diz qual botão "Baixar X" está ocupado); `null` nos outros tipos. */
  model: string | null
  state: JobState
  /** Passo atual (1-based). */
  step: number
  steps: number
  /** scan | chunk | embed */
  phase: string | null
  done: number | null
  total: number | null
  etaSeconds: number | null
  /** Só na fase embed. */
  ratePerSecond: number | null
  /** Ex.: "Outra indexação estava rodando; este pedido ficou agendado." */
  note: string | null
  error: string | null
  /** Últimas 20 linhas. */
  logTail: string[]
  queuedAt: string
  startedAt: string | null
  finishedAt: string | null
}

export interface DiscoverItem {
  /** Token opaco novo (não o mesmo passado a `discover`) - é isso que `enqueueJob({kind:'add-project', ...})` recebe como `folderToken`. */
  token: string
  /** Só para exibir - nunca é o que o renderer manda de volta como argumento. */
  path: string
  name: string
  alreadyRegistered: boolean
  /** Repositório git sem `ragx.toml`: vira projeto novo (`ragx init`) se for marcado. */
  isNew: boolean
}

export interface DiscoverResult {
  items: DiscoverItem[]
  /** `true` quando a busca parou por orçamento de pastas (Fix round 1) - a lista pode estar incompleta. */
  truncated: boolean
}

export type OllamaMode = 'docker' | 'native' | 'none' | 'conflict'
export type GpuVendor = 'nvidia' | 'amd' | 'intel' | 'apple' | 'none' | 'unknown'
export interface OllamaEnvironment {
  platform: 'win32' | 'darwin' | 'linux'
  gpu: { vendor: GpuVendor; name: string | null }
  docker: { installed: boolean; running: boolean }
  container: { exists: boolean; running: boolean }
  native: { installed: boolean; path: string | null; running: boolean }
  canInstallNative: boolean
  apiUp: boolean
  /** Nomes de /api/tags, como vêm. */
  models: string[]
  mode: OllamaMode
  recommendation: { mode: 'docker' | 'native'; reason: string }
}
export interface OllamaBenchmark {
  ok: boolean
  chunksPerSecond: number | null
  processor: 'gpu' | 'cpu' | 'unknown'
  vramMB: number | null
  model: string | null
  measuredAt: string
  error: string | null
}

export interface RagxBridge {
  getSnapshot: () => Promise<Snapshot>
  onSnapshot: (cb: (snapshot: Snapshot) => void) => () => void
  getProjectStatus: (projectId: string) => Promise<unknown>
  runTrial: (projectId: string) => Promise<TrialResult>
  runSecurityScan: (projectId: string) => Promise<SecurityScanResult>
  getConnections: () => Promise<ConnectionCheck[]>
  /** Resultado de cada checagem de conexões feita pelo processo principal (polling de 30 s incluso). */
  onConnections: (cb: (checks: ConnectionCheck[]) => void) => () => void
  listJobs: () => Promise<JobView[]>
  onJobs: (cb: (jobs: JobView[]) => void) => () => void
  enqueueJob: (req: JobRequest) => Promise<JobView>
  cancelJob: (jobId: string) => Promise<boolean>
  /** `path` é só para exibir - o token é o que qualquer chamada seguinte (`discover`) usa. */
  pickFolder: () => Promise<{ token: string; path: string } | null>
  discover: (token: string) => Promise<DiscoverResult>
  getSettings: () => Promise<PanelSettings>
  setOnboardingDone: (done: boolean) => Promise<void>
}

declare global {
  interface Window {
    ragx: RagxBridge
  }
}

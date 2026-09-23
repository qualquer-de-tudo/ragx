import { resolveJob, JobRejected, type CatalogContext, type ResolvedJob } from './jobs/catalog'
import type { DiscoverResult as DiscoverProjectsResult } from './projects/discovery'
import type { PanelSettings } from './settings'
import type {
  ConnectionCheck,
  DiscoverItem,
  DiscoverResult,
  JobRequest,
  JobView,
  ProjectSnapshot,
  SecurityScanResult,
  Snapshot,
  TrialResult,
} from '../src/types/ragx-bridge'

/**
 * Chaves aceitas num `JobRequest` vindo do renderer. Qualquer chave fora
 * desta lista é recusada aqui, antes mesmo de `resolveJob` (Task 5) olhar
 * para `kind` - um renderer comprometido mandando `{kind:'update',
 * projectId:'a', path:'C:/x'}` não pode injetar um campo extra que algum
 * código futuro do catálogo passe a ler sem querer.
 */
const JOB_REQUEST_KEYS: ReadonlySet<string> = new Set(['kind', 'projectId', 'folderToken', 'model', 'installHooks'])

export interface QueueLike {
  enqueue: (job: ResolvedJob) => JobView
  cancel: (id: string) => boolean
  list: () => JobView[]
}

export interface FolderTokensLike {
  issue: (path: string) => string
  get: (token: string) => string | undefined
}

export interface HandlerDeps {
  /** Reconstrói o snapshot (git, status.json, etc.) e atualiza o cache usado por `getCachedSnapshot`. */
  buildSnapshot: () => Promise<Snapshot>
  /** Último snapshot já construído (pelo polling ou por uma chamada anterior a `buildSnapshot`), sem reconstruir. */
  getCachedSnapshot: () => Snapshot | null
  runRagxCommand: (cwd: string, args: string[]) => Promise<unknown>
  checkAll: (snapshot: Snapshot) => Promise<ConnectionCheck[]>
  /**
   * Avisa o renderer (`ragx:connections`) a cada checagem terminada, venha
   * ela do polling de 30 s, do startup, de uma tarefa de conexão que terminou
   * ou de um "Verificar agora". É o único poller de conexões.
   */
  publishConnections?: (checks: ConnectionCheck[]) => void
  resetRagxCache: () => void
  queue: QueueLike
  folderTokens: FolderTokensLike
  discoverProjects: (root: string, registeredPaths: Set<string>) => DiscoverProjectsResult
  /** Abre o diálogo nativo de escolha de pasta; `null` quando o usuário cancela. Injetável (decisão 8) para o teste nunca precisar do Electron de verdade. */
  showOpenDialog: () => Promise<string | null>
  readSettings: () => PanelSettings
  writeSettings: (s: PanelSettings) => void
}

function rejected(message: string): Error {
  return new Error(`pedido recusado: ${message}`)
}

function validateJobRequestShape(input: unknown): JobRequest {
  if (typeof input !== 'object' || input === null || Array.isArray(input)) {
    throw rejected('formato de pedido inválido')
  }
  for (const key of Object.keys(input)) {
    if (!JOB_REQUEST_KEYS.has(key)) {
      throw rejected(`campo desconhecido: ${key}`)
    }
  }
  if (typeof (input as { kind?: unknown }).kind !== 'string') {
    throw rejected('kind precisa ser texto')
  }
  return input as JobRequest
}

export function createHandlers(deps: HandlerDeps) {
  let inFlightConnections: Promise<ConnectionCheck[]> | null = null

  async function runConnectionChecks(): Promise<ConnectionCheck[]> {
    deps.resetRagxCache()
    let snapshot = deps.getCachedSnapshot()
    if (snapshot === null) snapshot = await deps.buildSnapshot()
    const checks = await deps.checkAll(snapshot)
    deps.publishConnections?.(checks)
    return checks
  }

  function cachedProjects(): ProjectSnapshot[] {
    return deps.getCachedSnapshot()?.projects ?? []
  }

  function catalogContext(): CatalogContext {
    return {
      projectById: (id) => {
        const p = cachedProjects().find((proj) => proj.id === id)
        return p ? { id: p.id, name: p.name, path: p.path } : undefined
      },
      folderByToken: (token) => deps.folderTokens.get(token),
    }
  }

  /**
   * Todo handler que age sobre um projeto existente (`getProjectStatus`,
   * `runTrial`, `runSecurityScan`) valida o `projectId` contra o último
   * snapshot conhecido (o registro do hub) - nunca aceita um caminho vindo
   * do renderer. O caminho usado como `cwd` do processo sempre vem daqui,
   * nunca do pedido em si (decisão 4 do plano).
   */
  function requireLocalProject(projectIdUnknown: unknown): ProjectSnapshot {
    if (typeof projectIdUnknown !== 'string' || projectIdUnknown.length === 0) {
      throw rejected('projectId precisa ser texto')
    }
    const project = cachedProjects().find((p) => p.id === projectIdUnknown)
    if (project === undefined) {
      throw rejected(`projeto desconhecido: ${projectIdUnknown}`)
    }
    if (project.path === null) {
      throw rejected(`projeto "${project.name}" não tem pasta local (só federação)`)
    }
    return project
  }

  return {
    getSnapshot(): Promise<Snapshot> {
      return deps.buildSnapshot()
    },

    async getProjectStatus(projectIdUnknown: unknown): Promise<unknown> {
      const project = requireLocalProject(projectIdUnknown)
      return deps.runRagxCommand(project.path as string, ['status', '--json'])
    },

    async runTrial(projectIdUnknown: unknown): Promise<TrialResult> {
      const project = requireLocalProject(projectIdUnknown)
      return deps.runRagxCommand(project.path as string, ['trial', '--json']) as Promise<TrialResult>
    },

    async runSecurityScan(projectIdUnknown: unknown): Promise<SecurityScanResult> {
      const project = requireLocalProject(projectIdUnknown)
      return deps.runRagxCommand(project.path as string, ['security', 'scan', '.', '--json']) as Promise<SecurityScanResult>
    },

    /**
     * Reseta o cache do executável ragx (um `ragx` instalado depois da
     * janela abrir só é visto de novo assim), e roda as checagens contra o
     * último snapshot - constrói um primeiro se o polling ainda não rodou,
     * senão a checagem do Ollama reportaria "ok" achando que nenhum modelo
     * é necessário (decisão 2 do plano).
     *
     * Uma checagem por vez: quem chama no meio de uma em andamento (o
     * polling, o startup e o "Verificar agora" do renderer podem coincidir)
     * recebe o mesmo resultado em vez de disparar outra.
     */
    getConnections(): Promise<ConnectionCheck[]> {
      if (inFlightConnections) return inFlightConnections
      const run: Promise<ConnectionCheck[]> = runConnectionChecks().finally(() => {
        if (inFlightConnections === run) inFlightConnections = null
      })
      inFlightConnections = run
      return run
    },

    listJobs(): JobView[] {
      return deps.queue.list()
    },

    enqueueJob(reqUnknown: unknown): JobView {
      const req = validateJobRequestShape(reqUnknown)
      try {
        const resolved = resolveJob(req, catalogContext())
        return deps.queue.enqueue(resolved)
      } catch (err) {
        if (err instanceof JobRejected) throw rejected(err.message)
        throw err
      }
    },

    cancelJob(jobIdUnknown: unknown): boolean {
      if (typeof jobIdUnknown !== 'string' || jobIdUnknown.length === 0) {
        throw rejected('jobId precisa ser texto')
      }
      return deps.queue.cancel(jobIdUnknown)
    },

    async pickFolder(): Promise<{ token: string; path: string } | null> {
      const chosen = await deps.showOpenDialog()
      if (chosen === null) return null
      return { token: deps.folderTokens.issue(chosen), path: chosen }
    },

    /**
     * `token` veio de um `pickFolder()` anterior. Cada item achado ganha o
     * seu PRÓPRIO token novo (nunca reaproveita o de entrada) - o renderer
     * nunca vê o caminho de disco de um jeito que possa mandar de volta como
     * argumento; só o token serve para isso (ex.: `add-project`).
     */
    discover(tokenUnknown: unknown): DiscoverResult {
      if (typeof tokenUnknown !== 'string' || tokenUnknown.length === 0) {
        throw rejected('token precisa ser texto')
      }
      const root = deps.folderTokens.get(tokenUnknown)
      if (root === undefined) {
        throw rejected(`token de pasta desconhecido: ${tokenUnknown}`)
      }

      const registeredPaths = new Set(
        cachedProjects()
          .map((p) => p.path)
          .filter((p): p is string => p !== null),
      )
      const { items, truncated } = deps.discoverProjects(root, registeredPaths)
      const mapped: DiscoverItem[] = items.map((f) => ({
        token: deps.folderTokens.issue(f.path),
        path: f.path,
        name: f.name,
        alreadyRegistered: f.alreadyRegistered,
        isNew: f.isNew,
      }))
      return { items: mapped, truncated }
    },

    getSettings(): PanelSettings {
      return deps.readSettings()
    },

    setOnboardingDone(doneUnknown: unknown): void {
      if (typeof doneUnknown !== 'boolean') {
        throw rejected('done precisa ser booleano')
      }
      deps.writeSettings({ onboardingDone: doneUnknown })
    },
  }
}

export type Handlers = ReturnType<typeof createHandlers>

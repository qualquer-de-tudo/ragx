import type { BundleInfo } from './bootstrap/bundle'
import { resolveJob, JobRejected, MODEL_PATTERN, type CatalogContext, type ResolvedJob } from './jobs/catalog'
import { createCoalescedRun } from './system/coalesced-run'
import type { DiscoverResult as DiscoverProjectsResult } from './projects/discovery'
import type { PanelSettings, RendererSettings } from './settings'
import type {
  ConnectionCheck,
  DiscoverItem,
  DiscoverResult,
  JobRequest,
  JobView,
  OllamaBenchmark,
  OllamaEnvironment,
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
  /** Último ambiente Ollama detectado; alimenta os passos condicionais do catálogo. */
  getOllamaEnv?: () => OllamaEnvironment | null
  /** Modelos de embedding exigidos pelos projetos com provider ollama. */
  getRequiredModels?: () => string[]
  /** Modo do Ollama escolhido por último (persistido); `null` se nunca escolheu. */
  getPreferredOllamaMode?: () => 'docker' | 'native' | null
  /** Pacote de instalação da CLI que o `.exe` leva (já conferido); lança `BundleError` se ausente. */
  getBundle?: () => BundleInfo
  /** Caminho absoluto do `ragx.exe` para o registro do MCP. */
  getRagxExe?: () => string
  /** Mede embeddings/s. `model` é escolhido aqui no processo principal; `null` = modelo padrão. */
  runOllamaBenchmark: (model: string | null) => Promise<OllamaBenchmark>
}

function rejected(message: string): Error {
  return new Error(`pedido recusado: ${message}`)
}

const MAX_ECHO_LENGTH = 60

/** Valor vindo do renderer repetido numa mensagem de erro: cortado, para um texto enorme não inundar o log. */
function echo(value: unknown): string {
  const text = String(value)
  return text.length > MAX_ECHO_LENGTH ? `${text.slice(0, MAX_ECHO_LENGTH)}…` : text
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
  // `model` presente precisa ser um nome de modelo válido em QUALQUER kind,
  // não só no `ollama-pull` (onde o catálogo já confere): um valor hostil
  // nunca passa daqui, mesmo num kind que hoje o ignora.
  if ('model' in input) {
    const model = (input as { model?: unknown }).model
    if (model !== undefined && (typeof model !== 'string' || !MODEL_PATTERN.test(model))) {
      throw rejected(`nome de modelo inválido: ${echo(model)}`)
    }
  }
  return input as JobRequest
}

function benchmarkFailure(model: string | null, err: unknown): OllamaBenchmark {
  return {
    ok: false,
    chunksPerSecond: null,
    processor: 'unknown',
    vramMB: null,
    model,
    measuredAt: new Date().toISOString(),
    error: `Falha ao medir o Ollama: ${err instanceof Error ? err.message : String(err)}`,
  }
}

/** Benchmark guardado com o modo do Ollama em que foi medido. */
interface StoredBenchmark {
  benchmark: OllamaBenchmark
  mode: OllamaEnvironment['mode'] | null
}

export function createHandlers(deps: HandlerDeps) {
  let inFlightBenchmark: Promise<OllamaBenchmark> | null = null
  let lastBenchmark: StoredBenchmark | null = null
  // Sobe a cada `clearLastBenchmark`: uma medição que começou antes não é guardada.
  let benchmarkGeneration = 0

  function currentMode(): OllamaEnvironment['mode'] | null {
    try {
      return deps.getOllamaEnv?.()?.mode ?? null
    } catch {
      return null
    }
  }

  /** Primeiro modelo requerido com nome válido; `null` = o benchmark usa o padrão. */
  function benchmarkModel(): string | null {
    let models: unknown[]
    try {
      models = deps.getRequiredModels?.() ?? []
    } catch {
      return null
    }
    const first = models.find((m): m is string => typeof m === 'string' && MODEL_PATTERN.test(m))
    return first ?? null
  }

  async function measure(): Promise<OllamaBenchmark> {
    const model = benchmarkModel()
    const mode = currentMode()
    const generation = benchmarkGeneration
    let result: OllamaBenchmark
    try {
      result = await deps.runOllamaBenchmark(model)
    } catch (err) {
      result = benchmarkFailure(model, err)
    }
    if (generation === benchmarkGeneration) lastBenchmark = { benchmark: result, mode }
    return result
  }

  async function runConnectionChecks(): Promise<ConnectionCheck[]> {
    deps.resetRagxCache()
    let snapshot = deps.getCachedSnapshot()
    if (snapshot === null) snapshot = await deps.buildSnapshot()
    const checks = await deps.checkAll(snapshot)
    deps.publishConnections?.(checks)
    return checks
  }

  const connections = createCoalescedRun(runConnectionChecks)

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
      ollamaEnv: deps.getOllamaEnv,
      requiredModels: deps.getRequiredModels,
      preferredOllamaMode: deps.getPreferredOllamaMode,
      bundle: deps.getBundle,
      ragxExe: deps.getRagxExe,
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
      return connections.join()
    },

    /**
     * Checagem pedida pelo processo principal quando uma tarefa de conexão
     * termina (não é um canal de IPC). Se já tem uma checagem em andamento,
     * ela começou ANTES do fim da tarefa: agenda exatamente mais uma depois
     * dela, para o resultado final refletir o estado novo.
     */
    recheckConnections(): Promise<ConnectionCheck[]> {
      return connections.fresh()
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

    /** Só `onboardingDone` sai para o renderer; o resto das configurações fica aqui. */
    getSettings(): RendererSettings {
      return { onboardingDone: deps.readSettings().onboardingDone }
    },

    setOnboardingDone(doneUnknown: unknown): void {
      if (typeof doneUnknown !== 'boolean') {
        throw rejected('done precisa ser booleano')
      }
      // Lê, altera e grava: não apaga o modo preferido do Ollama.
      deps.writeSettings({ ...deps.readSettings(), onboardingDone: doneUnknown })
    },

    /**
     * Benchmark de embeddings. O modelo é escolhido aqui (o primeiro
     * requerido pelos projetos), nunca pelo renderer. Um por vez: quem pede
     * no meio de uma medição recebe o mesmo resultado. Nunca rejeita.
     */
    runOllamaBenchmark(): Promise<OllamaBenchmark> {
      if (inFlightBenchmark) return inFlightBenchmark
      const run: Promise<OllamaBenchmark> = measure().finally(() => {
        if (inFlightBenchmark === run) inFlightBenchmark = null
      })
      inFlightBenchmark = run
      return run
    },

    /**
     * Último benchmark medido nesta sessão (para a checagem do Ollama);
     * `null` se nenhum ou se o Ollama mudou de modo desde a medição (a
     * velocidade do Docker não diz nada sobre o local, e vice-versa).
     */
    getLastBenchmark(): OllamaBenchmark | null {
      if (lastBenchmark === null) return null
      if (lastBenchmark.mode !== currentMode()) return null
      return lastBenchmark.benchmark
    },

    /** Esquece o benchmark: uma troca, parada ou início do Ollama terminou (processo principal, não é canal de IPC). */
    clearLastBenchmark(): void {
      lastBenchmark = null
      benchmarkGeneration += 1
    },
  }
}

export type Handlers = ReturnType<typeof createHandlers>

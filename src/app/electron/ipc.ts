import os from 'node:os'
import type { BundleInfo } from './bootstrap/bundle'
import { resolveJob, JobRejected, MODEL_PATTERN, type CatalogContext, type ResolvedJob } from './jobs/catalog'
import { createCoalescedRun } from './system/coalesced-run'
import type { DiscoverResult as DiscoverProjectsResult } from './projects/discovery'
import { DEFAULT_ON_KEYS, PREFERENCE_KEYS, THEMES, parsePricing, type PanelSettings, type PreferenceKey, type RendererSettings } from './settings'
import { parseContextPreview } from './data/context-preview'
import type { ContextPreview } from './data/types'
import type {
  ClaudeIntegration,
  ClaudeProfile,
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
const MAX_QUESTION_LENGTH = 500
const PREVIEW_TIMEOUT_MS = 60_000

const PRICING_KEYS: ReadonlySet<string> = new Set(['currency', 'perMTokInput'])

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
  runRagxCommand: (cwd: string, args: string[], opts?: { timeoutMs?: number; stdin?: string }) => Promise<unknown>
  /** `light`: o tick de fundo (RAGX-0173), que evita processos; sem a opção, a checagem completa. */
  checkAll: (snapshot: Snapshot, opts?: { light?: boolean }) => Promise<ConnectionCheck[]>
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

/** A lista de perfis de `ragx claude status --json`, conferida item a item; o que não tem a forma certa fica de fora. */
export function parseClaudeProfiles(value: unknown): ClaudeProfile[] {
  if (!Array.isArray(value)) return []
  const text = (v: unknown, fallback: string) => (typeof v === 'string' && v.length > 0 ? v : fallback)
  return value.flatMap((item): ClaudeProfile[] => {
    if (typeof item !== 'object' || item === null) return []
    const r = item as Record<string, unknown>
    if (typeof r.id !== 'string' || r.id.length === 0 || typeof r.enabled !== 'boolean') return []
    return [{
      id: r.id,
      name: text(r.name, r.id),
      label: text(r.label, r.id),
      dir: text(r.dir, ''),
      enabled: r.enabled,
      hint: r.hint === true,
      touch: r.touch === true,
      nudge: r.nudge === true,
      added: r.added === true,
    }]
  })
}

function rejected(message: string): Error {
  return new Error(`pedido recusado: ${message}`)
}

const MAX_ECHO_LENGTH = 60
const TRIAL_TIMEOUT_MS = 240_000
/** Indexações por página da linha do tempo. */
export const RUNS_PAGE = 10
const MAX_RUNS_OFFSET = 100_000

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
  let inFlightPreview = false
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

  async function runConnectionChecks(light = false): Promise<ConnectionCheck[]> {
    deps.resetRagxCache()
    let snapshot = deps.getCachedSnapshot()
    if (snapshot === null) snapshot = await deps.buildSnapshot()
    const checks = light ? await deps.checkAll(snapshot, { light: true }) : await deps.checkAll(snapshot)
    deps.publishConnections?.(checks)
    return checks
  }

  let fullChecksRunning = 0
  const connections = createCoalescedRun(async () => {
    fullChecksRunning += 1
    try {
      return await runConnectionChecks()
    } finally {
      fullChecksRunning -= 1
    }
  })
  const lightConnections = createCoalescedRun(() => runConnectionChecks(true))

  let claudeChain: Promise<unknown> = Promise.resolve()

  /**
   * `ragx claude ...` é global (mexe em `~/.claude.json`), então roda na pasta
   * do usuário e não num projeto. A CLI responde JSON mesmo quando falha
   * (`error`), e a resposta é conferida: o renderer só recebe `{ enabled }`.
   */
  async function claudeCommand(args: string[]): Promise<ClaudeIntegration> {
    const out = (await deps.runRagxCommand(os.homedir(), args)) as {
      enabled?: unknown
      error?: unknown
      profiles?: unknown
    } | null
    if (out !== null && typeof out === 'object' && typeof out.error === 'string') {
      throw new Error(`Não consegui alterar o Claude Code: ${out.error}`)
    }
    if (out === null || typeof out !== 'object' || (typeof out.enabled !== 'boolean' && !Array.isArray(out.profiles))) {
      throw new Error('resposta inesperada de "ragx claude"')
    }
    const profiles = parseClaudeProfiles(out.profiles)
    // `profiles add/remove` não dizem `enabled`: ligado é todos os perfis ligados, como no `status`.
    const enabled = typeof out.enabled === 'boolean' ? out.enabled : profiles.length > 0 && profiles.every((p) => p.enabled)
    return { enabled, profiles }
  }

  /** Um pedido por vez no Claude Code: dois cliques rápidos não gravam a mesma configuração juntos. */
  function inClaudeChain<T>(fn: () => Promise<T>): Promise<T> {
    const run = claudeChain.then(fn)
    claudeChain = run.catch(() => undefined)
    return run
  }

  /** O perfil tem de ser um dos que a CLI acabou de listar: o id nunca vira argumento sem conferência. */
  async function knownProfile(idUnknown: unknown): Promise<ClaudeProfile> {
    if (typeof idUnknown !== 'string' || idUnknown.length === 0 || idUnknown.length > 200) {
      throw rejected('perfil precisa ser um id de perfil')
    }
    const atual = await claudeCommand(['claude', 'status', '--json'])
    const perfil = atual.profiles.find((p) => p.id === idUnknown)
    if (!perfil) throw rejected(`perfil desconhecido: ${idUnknown}`)
    return perfil
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

    /**
     * Preview do `build_context` (RAGX-0187): o que o agente receberia para uma pergunta. A pergunta vai SÓ por stdin
     * (nunca no argv, em log ou em mensagem de erro) com o cache desligado, e a saída passa por `parseContextPreview`,
     * que descarta `query` e `content`. Um preview por vez.
     */
    async previewContext(projectIdUnknown: unknown, questionUnknown: unknown): Promise<ContextPreview> {
      const project = requireLocalProject(projectIdUnknown)
      // Nenhuma das mensagens abaixo repete a pergunta.
      if (typeof questionUnknown !== 'string') throw rejected('a pergunta precisa ser texto')
      const question = questionUnknown.trim()
      if (question.length === 0) throw rejected('a pergunta está vazia')
      if (question.length > MAX_QUESTION_LENGTH) throw rejected(`a pergunta passa de ${MAX_QUESTION_LENGTH} caracteres`)
      if (question.includes('\0')) throw rejected('a pergunta tem caractere inválido')
      if (inFlightPreview) throw rejected('Já há uma pré-visualização em andamento')
      inFlightPreview = true
      try {
        const raw = await deps.runRagxCommand(
          project.path as string,
          ['context', '--query-stdin', '--format', 'json', '--no-cache'],
          { timeoutMs: PREVIEW_TIMEOUT_MS, stdin: question },
        )
        const preview = parseContextPreview(raw)
        if (preview === null) throw new Error('resposta inesperada de ragx context')
        return preview
      } finally {
        inFlightPreview = false
      }
    },

    async runTrial(projectIdUnknown: unknown): Promise<TrialResult> {
      const project = requireLocalProject(projectIdUnknown)
      // Sem `queries.yaml` o trial gera as consultas e roda o build_context de
      // cada uma: com o Ollama em CPU passa de um minuto.
      return deps.runRagxCommand(project.path as string, ['trial', '--json'], {
        timeoutMs: TRIAL_TIMEOUT_MS,
      }) as Promise<TrialResult>
    },

    /**
     * Uma página do histórico de indexações (`ragx runs`), para o "Carregar
     * mais" da linha do tempo. O tamanho da página é fixo aqui; do renderer
     * só vem o deslocamento, conferido.
     */
    async getIndexRuns(projectIdUnknown: unknown, offsetUnknown: unknown): Promise<unknown> {
      const project = requireLocalProject(projectIdUnknown)
      if (typeof offsetUnknown !== 'number' || !Number.isInteger(offsetUnknown) || offsetUnknown < 0 || offsetUnknown > MAX_RUNS_OFFSET) {
        throw rejected('offset precisa ser um inteiro não negativo')
      }
      return deps.runRagxCommand(project.path as string, [
        'runs',
        '--limit',
        String(RUNS_PAGE),
        '--offset',
        String(offsetUnknown),
        '--json',
      ])
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
     * A checagem LEVE do tick de fundo (30 s): interna, NÃO é um canal de IPC (o renderer nunca a pede).
     * Com uma checagem completa em andamento, junta-se a ela em vez de rodar outra.
     */
    getConnectionsLight(): Promise<ConnectionCheck[]> {
      return fullChecksRunning > 0 ? connections.join() : lightConnections.join()
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
      const { onboardingDone, pricing, tray, notifyStale, autoUpdate, autoSetup, theme } = deps.readSettings()
      return {
        onboardingDone,
        ...(pricing === undefined ? {} : { pricing }),
        ...(theme === undefined ? {} : { theme }),
        ...(tray === true ? { tray } : {}),
        ...(notifyStale === true ? { notifyStale } : {}),
        // ligada por padrão: só o `false` explícito sai (ausente = ligada)
        ...(autoUpdate === false ? { autoUpdate } : {}),
        ...(autoSetup === false ? { autoSetup } : {}),
      }
    },

    /** Tema do painel (RAGX-0193): lista fechada de três literais; `dark` (o padrão) apaga o campo. */
    setTheme(themeUnknown: unknown): void {
      if (typeof themeUnknown !== 'string' || !(THEMES as readonly string[]).includes(themeUnknown)) {
        throw rejected('tema desconhecido')
      }
      const { theme: _old, ...rest } = deps.readSettings()
      void _old
      deps.writeSettings(themeUnknown === 'dark' ? rest : { ...rest, theme: themeUnknown as 'light' | 'system' })
    },

    /**
     * Liga ou desliga uma preferência booleana (RAGX-0191). Chave de LISTA FECHADA e valor booleano; `false` apaga o
     * campo (o padrão é desligado). Não é tarefa da fila nem abre processo.
     */
    setPreference(keyUnknown: unknown, valueUnknown: unknown): void {
      if (typeof keyUnknown !== 'string' || !(PREFERENCE_KEYS as readonly string[]).includes(keyUnknown)) {
        throw rejected('preferência desconhecida')
      }
      if (typeof valueUnknown !== 'boolean') throw rejected('o valor precisa ser booleano')
      const key = keyUnknown as PreferenceKey
      const current = deps.readSettings()
      const { [key]: _old, ...rest } = current
      void _old
      // as ligadas por padrão (`autoUpdate`, `autoSetup`): desligar grava `false` (apagar a chave as ligaria de novo)
      deps.writeSettings(
        valueUnknown ? { ...rest, [key]: true } : DEFAULT_ON_KEYS.includes(key) ? { ...rest, [key]: false } : rest,
      )
    },

    /**
     * Preço informado pela pessoa (RAGX-0186). Só enum de moeda e número: recusa chave desconhecida, moeda fora do
     * conjunto e preço fora de `0 < p <= 10000`; `null` limpa. Não é tarefa da fila nem abre processo.
     */
    setPricing(pricingUnknown: unknown): void {
      const current = deps.readSettings()
      if (pricingUnknown === null) {
        const { pricing: _removed, ...rest } = current
        void _removed
        deps.writeSettings(rest)
        return
      }
      if (typeof pricingUnknown !== 'object' || Array.isArray(pricingUnknown)) {
        throw rejected('preço precisa ser um objeto ou null')
      }
      for (const key of Object.keys(pricingUnknown as object)) {
        if (!PRICING_KEYS.has(key)) throw rejected(`campo desconhecido: ${key}`)
      }
      const pricing = parsePricing(pricingUnknown)
      if (pricing === null) throw rejected('moeda ou preço inválido')
      deps.writeSettings({ ...current, pricing })
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

    /** Estado atual do interruptor, lido de `~/.claude.json` pela própria CLI. */
    getClaudeIntegration(): Promise<ClaudeIntegration> {
      return claudeCommand(['claude', 'status', '--json'])
    },

    /**
     * Liga/desliga o RAGX no Claude Code (global). Um pedido por vez: dois
     * cliques rápidos não gravam o `~/.claude.json` ao mesmo tempo, e o
     * último vence. `on` grava o caminho absoluto do `ragx.exe`, como o
     * registro do instalador: cliente gráfico nem sempre herda o PATH.
     */
    setClaudeIntegration(enabledUnknown: unknown): Promise<ClaudeIntegration> {
      if (typeof enabledUnknown !== 'boolean') {
        throw rejected('enabled precisa ser booleano')
      }
      const exe = enabledUnknown ? deps.getRagxExe?.() : undefined
      const args = enabledUnknown
        ? ['claude', 'on', ...(exe ? ['--command', exe] : []), '--json']
        : ['claude', 'off', '--json']
      return inClaudeChain(() => claudeCommand(args))
    },

    /** Liga ou desliga o RAGX num perfil só (`ragx claude on|off --profile`). */
    setClaudeProfile(idUnknown: unknown, enabledUnknown: unknown): Promise<ClaudeIntegration> {
      if (typeof enabledUnknown !== 'boolean') {
        throw rejected('enabled precisa ser booleano')
      }
      return inClaudeChain(async () => {
        const perfil = await knownProfile(idUnknown)
        const exe = enabledUnknown ? deps.getRagxExe?.() : undefined
        return claudeCommand(
          enabledUnknown
            ? ['claude', 'on', '--profile', perfil.id, ...(exe ? ['--command', exe] : []), '--json']
            : ['claude', 'off', '--profile', perfil.id, '--json'],
        )
      })
    },

    /**
     * Adiciona uma pasta de perfil do Claude Code e já liga o RAGX nela. A pasta
     * vem de um `pickFolder()` anterior, pelo token: o renderer nunca manda caminho.
     */
    addClaudeProfile(tokenUnknown: unknown): Promise<ClaudeIntegration> {
      if (typeof tokenUnknown !== 'string') throw rejected('token precisa ser texto')
      const dir = deps.folderTokens.get(tokenUnknown)
      if (dir === undefined) throw rejected('pasta desconhecida: escolha de novo')
      const exe = deps.getRagxExe?.()
      return inClaudeChain(() =>
        claudeCommand(['claude', 'profiles', 'add', dir, '--on', ...(exe ? ['--command', exe] : []), '--json']),
      )
    },

    /**
     * Tira um perfil adicionado à mão. Desliga o RAGX nele antes: para quem
     * clica "Remover", o esperado é o RAGX sair daquela conta, não só da lista.
     */
    removeClaudeProfile(idUnknown: unknown): Promise<ClaudeIntegration> {
      return inClaudeChain(async () => {
        const perfil = await knownProfile(idUnknown)
        if (!perfil.added) throw rejected('só dá para remover um perfil adicionado à mão')
        if (perfil.enabled) await claudeCommand(['claude', 'off', '--profile', perfil.id, '--json'])
        return claudeCommand(['claude', 'profiles', 'remove', perfil.dir, '--json'])
      })
    },

    /** Esquece o benchmark: uma troca, parada ou início do Ollama terminou (processo principal, não é canal de IPC). */
    clearLastBenchmark(): void {
      lastBenchmark = null
      benchmarkGeneration += 1
    },
  }
}

export type Handlers = ReturnType<typeof createHandlers>

import { app, BrowserWindow, dialog, ipcMain, powerMonitor } from 'electron'
import { randomUUID } from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { initSqlWasm } from './data/project-stats'
import { buildSnapshot } from './data/snapshot'
import { runRagxCommand } from './data/run-ragx-command'
import { ActivityTail } from './data/activity'
import { checkAll, defaultCheckDeps, resetRagxVersionCache } from './connections/checks'
import { resetRagxCache, resolveRagx } from './system/ragx-exe'
import { execFileText } from './system/exec'
import { createRuntimeSampler, metricsFileFromEnv } from './system/runtime-metrics'
import { createPausablePoller, type PausablePoller } from './system/pausable-poller'
import { watchWindowActivity, type PowerLike, type WindowLike } from './system/window-activity'
import { acquireSingleInstance } from './single-instance'
import { parsePlan, type PanelState } from './system/runtime-summary'
import { findBundleDir, loadBundle, uvCommand } from './bootstrap/bundle'
import { afterRagxInstall } from './bootstrap/post-install'
import { realPathDeps, removeFromUserPath } from './bootstrap/path-user'
import { uninstallCli } from './bootstrap/uninstall'
import { JobQueue, defaultSpawn } from './jobs/queue'
import { resolveJob } from './jobs/catalog'
import { defaultVerifyDeps, verifyJob } from './jobs/verify'
import { CONNECTION_JOB_KINDS, justFinishedJobs } from './jobs/transitions'
import { isInsideGitWorkTree } from './data/git'
import { DEV_SERVER_URL, isDevServerUrl } from './navigation'
import { FolderTokens } from './projects/tokens'
import { discoverProjects } from './projects/discovery'
import { readSettings, updateSettings, writeSettings } from './settings'
import { createHandlers } from './ipc'
import { defaultEnvDeps, detectOllama, detectOllamaLight, type LightState } from './ollama/environment'
import { defaultBenchDeps, runOllamaBenchmark } from './ollama/benchmark'
import { resetOllamaCache } from './ollama/paths'
import {
  conditionFrom,
  createOllamaEnvCache,
  defaultWaitDeps,
  distinctRequiredModels,
  ollamaFollowUps,
  waitForApi,
} from './ollama/wiring'
import type { ConnectionCheck, JobView, Snapshot } from '../src/types/ragx-bridge'

// RAGX-0177: com `RAGX_PANEL_METRICS` o painel mede o próprio consumo, e mede a casca de PRODUÇÃO
// (`dist/index.html`, sem DevTools), mesmo rodando sem empacotar.
const METRICS_FILE = metricsFileFromEnv(process.env)
const isDev = !app.isPackaged && METRICS_FILE === null

// Modos sem janela, chamados pelo instalador NSIS (`build/installer.nsh`).
const BOOTSTRAP = process.argv.includes('--bootstrap')
const UNINSTALL_CLI = process.argv.includes('--uninstall-cli')
const REMOVE_DATA = process.argv.includes('--remove-data')
const HEADLESS = BOOTSTRAP || UNINSTALL_CLI

const SNAPSHOT_POLL_MS = 5000
const CONNECTIONS_POLL_MS = 30_000
/** Atividade: só lê o que foi acrescentado aos logs, então dá para ser curto. */
const ACTIVITY_POLL_MS = 1500
const JOBS_THROTTLE_MS = 250

let mainWindow: BrowserWindow | null = null
// RAGX-0171: os três pollers pausam com a janela fora da vista (minimizada, oculta, tela bloqueada, suspenso)
let snapshotPoller: PausablePoller | null = null
let connectionsPoller: PausablePoller | null = null
let activityPoller: PausablePoller | null = null
let stopWatchingActivity: (() => void) | null = null
/** O painel está sendo visto? Com `false`, o fim de uma tarefa só marca o snapshot como sujo. */
let panelActive = true
/** Algo mudou (uma tarefa terminou) enquanto o painel estava fora da vista: reconstrói na volta. */
let snapshotStale = false
const activity = new ActivityTail()

// Último snapshot/checagens conhecidos - fonte de verdade para validar
// `projectId`/caminhos nos handlers de IPC (nunca o pedido do renderer) e
// para calcular `connectionsHealth` sem esperar a próxima janela de 30s.
let latestSnapshot: Snapshot | null = null
let latestConnections: ConnectionCheck[] | null = null

const folderTokens = new FolderTokens()

function worstConnectionsState(checks: ConnectionCheck[]): 'ok' | 'warn' | 'error' {
  if (checks.some((c) => c.state === 'error')) return 'error'
  if (checks.some((c) => c.state === 'warn')) return 'warn'
  return 'ok'
}

function withConnectionsHealth(snapshot: Snapshot): Snapshot {
  return { ...snapshot, connectionsHealth: latestConnections ? worstConnectionsState(latestConnections) : null }
}

// Fix round 1 (MINOR 1/2): uma única reconstrução por vez, compartilhada
// entre o polling de 5s, o handler `ragx:getSnapshot` e o push logo após uma
// tarefa terminar - `git` nunca roda em paralelo consigo mesmo, e uma
// chamada que chega no meio de uma reconstrução em andamento recebe o
// MESMO resultado em vez de disparar outra.
let inFlightSnapshot: Promise<Snapshot> | null = null

/** Quanto levou a última reconstrução do snapshot (só a medição de consumo lê). */
let lastSnapshotMs: number | null = null

function refreshSnapshot(): Promise<Snapshot> {
  if (inFlightSnapshot) return inFlightSnapshot
  const promise = (async () => {
    try {
      const started = Date.now()
      const s = await buildSnapshot()
      lastSnapshotMs = Date.now() - started
      latestSnapshot = s
      return withConnectionsHealth(s)
    } finally {
      inFlightSnapshot = null
    }
  })()
  inFlightSnapshot = promise
  return promise
}

// -- Ollama ------------------------------------------------------------

// Último ambiente detectado: alimenta o catálogo (`CatalogContext.ollamaEnv`).
// Atualizado a cada checagem de conexões (startup, polling de 30 s, fim de
// tarefa) e a cada condição de passo da fila, que sempre detecta de novo.
// A detecção LEVE (tick de 30 s) lembra quando o `docker ps` rodou pela última vez (RAGX-0173).
const lightState: LightState = { lastDockerProbeAt: null }
const ollamaEnv = createOllamaEnvCache(
  async () => {
    lightState.lastDockerProbeAt = Date.now()
    return detectOllama(defaultEnvDeps())
  },
  (previous) => detectOllamaLight(defaultEnvDeps(), previous, lightState),
)

function userDataDir(): string {
  return app.getPath('userData')
}

function preferredOllamaMode(): 'docker' | 'native' | null {
  return readSettings(userDataDir()).ollamaMode ?? null
}

function persistOllamaMode(mode: 'docker' | 'native'): void {
  try {
    updateSettings(userDataDir(), { ollamaMode: mode })
  } catch (err) {
    console.error('nao foi possivel gravar o modo preferido do Ollama:', err)
  }
}

// -- fila de tarefas ---------------------------------------------------

const queue = new JobQueue(
  {
    spawn: defaultSpawn(),
    now: () => Date.now(),
    newId: () => randomUUID(),
    isGitRepo: (folder) => isInsideGitWorkTree(folder),
    verify: (job) => verifyJob(job, defaultVerifyDeps()),
    // Detecta NA HORA (passos anteriores da mesma tarefa mudam o ambiente).
    stepCondition: async (c) => conditionFrom(await ollamaEnv.fresh(), c),
    waitForOllamaApi: (timeoutMs) => waitForApi(timeoutMs, defaultWaitDeps()),
  },
  (jobs) => onJobsChange(jobs),
)

let jobsThrottleTimer: ReturnType<typeof setTimeout> | null = null
let pendingJobs: JobView[] | null = null
let previousJobStates = new Map<string, JobView['state']>()

/** No máximo uma mensagem `ragx:jobs` a cada 250ms (borda de saída + a última pendente no fim da janela). */
function sendJobsThrottled(jobs: JobView[]): void {
  if (jobsThrottleTimer) {
    pendingJobs = jobs
    return
  }
  mainWindow?.webContents.send('ragx:jobs', jobs)
  jobsThrottleTimer = setTimeout(() => {
    jobsThrottleTimer = null
    if (pendingJobs) {
      const jobsToSend = pendingJobs
      pendingJobs = null
      sendJobsThrottled(jobsToSend)
    }
  }, JOBS_THROTTLE_MS)
}

function onJobsChange(jobs: JobView[]): void {
  // Sem janela não há o que atualizar: quem roda em modo headless espera a fila terminar.
  if (HEADLESS) return
  const finished = justFinishedJobs(previousJobStates, jobs)
  const justFinished = finished.length > 0
  previousJobStates = new Map(jobs.map((j) => [j.id, j.state]))

  // Tarefa do Ollama terminou (qualquer estado): o executável pode ter
  // mudado de lugar (`winget install`), e uma troca de modo concluída vira o
  // modo preferido. Uma detecção do ambiente em andamento começou antes do
  // fim da tarefa: é descartada, e o próximo pedido detecta de novo. Tudo
  // antes da checagem de conexões abaixo, que já vê o novo.
  const ollama = ollamaFollowUps(finished)
  if (ollama.resetCache) {
    resetOllamaCache()
    ollamaEnv.invalidate()
  }
  if (ollama.persistMode !== null) persistOllamaMode(ollama.persistMode)
  // Outro Ollama servindo (ou nenhum): a velocidade medida antes não vale.
  if (ollama.clearBenchmark) handlers.clearLastBenchmark()

  // Terminou uma correção de conexão ("Registrar", "Iniciar container",
  // "Baixar modelo", trocas de modo do Ollama): confere de novo. Se uma
  // checagem já está no ar (começou antes), roda mais uma depois dela. O
  // resultado chega ao renderer por `ragx:connections`, como o do polling.
  if (finished.some((j) => j.kind === 'ragx-install' && j.state === 'done')) {
    // O `ragx.exe` acabou de aparecer: refaz o cache do caminho e o PATH do
    // usuário ANTES de conferir as conexões, para o card já sair verde.
    resetRagxVersionCache() // o executável acabou de ser (re)instalado: a versão guardada é velha
    afterRagxInstall(postInstallDeps())
      .catch((err) => console.error('pos-instalacao do ragx falhou:', err))
      .then(() => handlers.recheckConnections())
      .catch((err) => console.error('checagem de conexoes falhou apos instalar o ragx:', err))
  } else if (finished.some((j) => CONNECTION_JOB_KINDS.has(j.kind))) {
    handlers.recheckConnections().catch((err) => console.error('checagem de conexoes falhou apos tarefa:', err))
  }

  sendJobsThrottled(jobs)

  // Uma tarefa terminou: o renderer precisa ver o snapshot atualizado sem
  // esperar até 5s pelo próximo tick do polling. Se já tem uma reconstrução
  // rodando, não dispara outra em paralelo - marca "dirty" pra rodar mais
  // uma assim que essa terminar, porque ela pode ter começado antes da
  // tarefa terminar de verdade e não refletir o resultado final (MINOR 2).
  // Com a janela fora da vista (RAGX-0171) não reconstrói: marca o snapshot como sujo e a volta o atualiza.
  // A fila e as tarefas NÃO pausam.
  if (justFinished) {
    if (panelActive) void pushSnapshotNow({ markDirtyIfBusy: true })
    else snapshotStale = true
  }
}

let snapshotDirtyAfterInFlight = false

function pushSnapshotNow(opts: { markDirtyIfBusy?: boolean } = {}): Promise<void> {
  if (inFlightSnapshot) {
    if (opts.markDirtyIfBusy) snapshotDirtyAfterInFlight = true
    return Promise.resolve() // já tem uma reconstrução em andamento - a batida de polling/o "dirty" acima cobre isso
  }
  return refreshSnapshot()
    .then(async (snapshot) => {
      snapshotStale = false
      mainWindow?.webContents.send('ragx:snapshot', snapshot)
      if (snapshotDirtyAfterInFlight) {
        snapshotDirtyAfterInFlight = false
        await pushSnapshotNow()
      }
    })
    .catch((err) => console.error('buildSnapshot() falhou apos tarefa terminar:', err))
}

// -- handlers de IPC -----------------------------------------------------

const handlers = createHandlers({
  buildSnapshot: refreshSnapshot,
  getCachedSnapshot: () => (latestSnapshot ? withConnectionsHealth(latestSnapshot) : null),
  runRagxCommand,
  checkAll: async (snapshot, opts) => {
    // Uma detecção do ambiente do Ollama por ciclo (`getConnections` já
    // garante um ciclo por vez); o card usa esse mesmo ambiente, sem um
    // segundo `docker ps`. `handlers` só é lido aqui, depois de criado.
    const env = await (opts?.light ? ollamaEnv.light() : ollamaEnv.fresh()).catch((err: unknown) => {
      console.error('detectOllama() falhou:', err)
      return null
    })
    // O modo preferido decide o texto do "Iniciar" (o mesmo que o catálogo roda).
    const checks = await checkAll(defaultCheckDeps(), snapshot, env, handlers.getLastBenchmark(), preferredOllamaMode())
    latestConnections = checks
    return checks
  },
  publishConnections: (checks) => {
    mainWindow?.webContents.send('ragx:connections', checks)
  },
  resetRagxCache,
  queue: {
    enqueue: (job) => queue.enqueue(job),
    cancel: (id) => queue.cancel(id),
    list: () => queue.list(),
  },
  folderTokens,
  discoverProjects,
  showOpenDialog: async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] })
    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
  },
  readSettings: () => readSettings(userDataDir()),
  writeSettings: (s) => writeSettings(userDataDir(), s),
  getOllamaEnv: () => ollamaEnv.get(),
  getRequiredModels: () => distinctRequiredModels(latestSnapshot),
  getPreferredOllamaMode: preferredOllamaMode,
  getBundle: () => loadBundle(),
  getRagxExe,
  // O resultado fica em `handlers.getLastBenchmark()` (a checagem do Ollama o usa).
  runOllamaBenchmark: (model) => runOllamaBenchmark(defaultBenchDeps(model)),
})

/**
 * Fix round 1 (MINOR 6): todo handler só atende pedidos cujo frame de
 * origem é o frame principal da própria janela do painel. `contextIsolation`
 * já impede o renderer de tocar em Node direto, mas isso fecha a outra
 * ponta - um iframe/popup que por algum motivo acabe carregado dentro do
 * processo (ex.: uma falha na regra de navegação abaixo) não herda acesso
 * ao `ragx:*` só por rodar no mesmo `WebContents`.
 */
function isTrustedSender(event: Electron.IpcMainInvokeEvent): boolean {
  return mainWindow !== null && event.senderFrame !== null && event.senderFrame === mainWindow.webContents.mainFrame
}

function handleIpc(channel: string, fn: (...args: unknown[]) => unknown): void {
  ipcMain.handle(channel, (event: Electron.IpcMainInvokeEvent, ...args: unknown[]) => {
    if (!isTrustedSender(event)) {
      throw new Error('pedido recusado: origem nao confiavel')
    }
    return fn(...args)
  })
}

handleIpc('ragx:getSnapshot', () => handlers.getSnapshot())
// Sem argumentos: o que já está em memória (24 h); o resto chega por `ragx:activity`.
handleIpc('ragx:getActivity', () => {
  pollActivity()
  return activity.recent()
})
handleIpc('ragx:getProjectStatus', (projectId: unknown) => handlers.getProjectStatus(projectId))
handleIpc('ragx:runTrial', (projectId: unknown) => handlers.runTrial(projectId))
handleIpc('ragx:getIndexRuns', (projectId: unknown, offset: unknown) => handlers.getIndexRuns(projectId, offset))
handleIpc('ragx:runSecurityScan', (projectId: unknown) => handlers.runSecurityScan(projectId))
handleIpc('ragx:getConnections', () => handlers.getConnections())
handleIpc('ragx:listJobs', () => handlers.listJobs())
handleIpc('ragx:enqueueJob', (req: unknown) => handlers.enqueueJob(req))
handleIpc('ragx:cancelJob', (jobId: unknown) => handlers.cancelJob(jobId))
handleIpc('ragx:pickFolder', () => handlers.pickFolder())
handleIpc('ragx:discover', (token: unknown) => handlers.discover(token))
handleIpc('ragx:getSettings', () => handlers.getSettings())
handleIpc('ragx:setOnboardingDone', (done: unknown) => handlers.setOnboardingDone(done))
// Sem argumentos: o que vier do renderer é descartado aqui.
handleIpc('ragx:run-ollama-benchmark', () => handlers.runOllamaBenchmark())
handleIpc('ragx:getClaudeIntegration', () => handlers.getClaudeIntegration())
handleIpc('ragx:setClaudeIntegration', (enabled: unknown) => handlers.setClaudeIntegration(enabled))
handleIpc('ragx:setClaudeProfile', (id: unknown, enabled: unknown) => handlers.setClaudeProfile(id, enabled))
handleIpc('ragx:addClaudeProfile', (token: unknown) => handlers.addClaudeProfile(token))
handleIpc('ragx:removeClaudeProfile', (id: unknown) => handlers.removeClaudeProfile(id))

// -- instalação da CLI (bootstrap) -----------------------------------------

/** Onde o `uv tool` põe o `ragx.exe`; é o mesmo lugar que `resolveRagx` olha por último. */
function getRagxExe(): string {
  return resolveRagx() ?? path.join(os.homedir(), '.local', 'bin', 'ragx.exe')
}

function postInstallDeps() {
  return { resetCache: resetRagxCache, resolveRagx: () => resolveRagx(), pathDeps: realPathDeps(userDataDir()) }
}

function logBootstrap(message: string): void {
  try {
    fs.mkdirSync(userDataDir(), { recursive: true })
    fs.appendFileSync(path.join(userDataDir(), 'bootstrap.log'), `${new Date().toISOString()} ${message}
`)
  } catch {
    // o log é só para diagnóstico; nunca derruba o instalador
  }
}

/** Enfileira o `ragx-install`; `null` (com o motivo no log) se o pacote falta ou já há um rodando. */
function enqueueRagxInstall(): JobView | null {
  try {
    const resolved = resolveJob(
      { kind: 'ragx-install' },
      { projectById: () => undefined, folderByToken: () => undefined, bundle: () => loadBundle(), ragxExe: getRagxExe },
    )
    return queue.enqueue(resolved)
  } catch (err) {
    logBootstrap(`ragx-install nao enfileirado: ${err instanceof Error ? err.message : String(err)}`)
    return null
  }
}

const BOOTSTRAP_TIMEOUT_MS = 15 * 60_000

/** `--bootstrap`: instala a CLI sem janela e devolve o código de saída (0 = ok). */
async function runBootstrapHeadless(): Promise<number> {
  const job = enqueueRagxInstall()
  if (job === null) return 1
  const deadline = Date.now() + BOOTSTRAP_TIMEOUT_MS
  for (;;) {
    const view = queue.list().find((j) => j.id === job.id)
    if (view && view.state !== 'queued' && view.state !== 'running') {
      if (view.state !== 'done') {
        logBootstrap(`ragx-install terminou em ${view.state}: ${view.error ?? 'sem detalhe'}`)
        return 1
      }
      const r = await afterRagxInstall(postInstallDeps())
      logBootstrap(r.found ? `ragx instalado (PATH alterado: ${String(r.pathAdded)})` : 'ragx-install terminou, mas o ragx.exe nao apareceu')
      return r.found ? 0 : 1
    }
    if (Date.now() > deadline) {
      logBootstrap('ragx-install passou de 15 minutos; desistindo')
      queue.cancel(job.id)
      return 1
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
}

/** `--uninstall-cli [--remove-data]`: desfaz o que o `ragx-install` fez; código 0 = sem erros. */
async function runUninstallHeadless(): Promise<number> {
  const pathDeps = realPathDeps(userDataDir())
  const result = await uninstallCli(
    { removeData: REMOVE_DATA },
    {
      exec: execFileText,
      ragxPath: () => resolveRagx(),
      uvPath: () => uvCommand(),
      removeFromPath: () => removeFromUserPath(pathDeps),
      rm: (p) => fs.promises.rm(p, { recursive: true, force: true }),
      homedir: os.homedir(),
    },
  )
  for (const step of result.steps) logBootstrap(`desinstalar: ${step}`)
  for (const error of result.errors) logBootstrap(`desinstalar ERRO: ${error}`)
  return result.errors.length === 0 ? 0 : 1
}

// -- polling ---------------------------------------------------------------

function startSnapshotPolling(): void {
  if (snapshotPoller) return
  // git pode ser lento - `pushSnapshotNow` já pula a batida se a anterior
  // ainda não terminou, para nunca rodar `git` em paralelo para o mesmo projeto.
  snapshotPoller = createPausablePoller({
    intervalMs: SNAPSHOT_POLL_MS,
    run: () => pushSnapshotNow(),
    onError: (err) => console.error('polling do snapshot falhou:', err),
  })
  snapshotPoller.start()
}

/**
 * Tela de atividade: lê o que os agentes e a CLI acrescentaram aos logs dos
 * projetos locais e empurra só os eventos novos. Os projetos vêm do último
 * snapshot; antes do primeiro, não há o que acompanhar.
 */
function pollActivity(): void {
  const snapshot = latestSnapshot
  if (!snapshot) return
  const sources = snapshot.projects
    .filter((p) => p.path !== null && p.exists)
    .map((p) => ({ id: p.id, name: p.name, path: p.path }))
  const novos = activity.poll(sources)
  if (novos.length > 0) mainWindow?.webContents.send('ragx:activity', novos)
}

function startActivityPolling(): void {
  if (activityPoller) return
  activityPoller = createPausablePoller({
    intervalMs: ACTIVITY_POLL_MS,
    run: () => pollActivity(),
    onError: (err) => console.error('pollActivity() falhou:', err),
  })
  activityPoller.start()
}

function startConnectionsPolling(): void {
  if (connectionsPoller) return
  // Único poller de conexões: `getConnections` já junta chamadas que chegam
  // no meio de uma checagem, e cada resultado vai para o renderer por
  // `ragx:connections` (`publishConnections`).
  connectionsPoller = createPausablePoller({
    intervalMs: CONNECTIONS_POLL_MS,
    // tick de fundo: a checagem LEVE (RAGX-0173); "Verificar agora", startup e fim de tarefa seguem completos
    run: () => handlers.getConnectionsLight(),
    onError: (err) => console.error('getConnectionsLight() falhou no polling:', err),
  })
  connectionsPoller.start()
}

/**
 * RAGX-0171: liga os pollers à visibilidade da janela. Fora da vista nada roda; na volta, um snapshot na
 * hora (se algo mudou ou já passou o intervalo), conexões só se a última tem mais de 30 s e uma passada de
 * atividade (cada poller decide pelo próprio intervalo ao ser reativado).
 */
function watchPanelActivity(win: BrowserWindow): void {
  stopWatchingActivity?.()
  // o `on` do Electron é sobrecarregado por evento: o tipo estreito `WindowLike` pede um cast
  stopWatchingActivity = watchWindowActivity(win as unknown as WindowLike, powerMonitor as unknown as PowerLike, (active) => {
    panelActive = active
    snapshotPoller?.setActive(active)
    connectionsPoller?.setActive(active)
    activityPoller?.setActive(active)
    if (active && snapshotStale) snapshotPoller?.runNow()
  })
}

// -- medição de consumo (RAGX-0177) ----------------------------------------

let panelState: PanelState = 'visible'

/**
 * Só com `RAGX_PANEL_METRICS`: amostra RAM/CPU/filhos a cada 5 s num JSONL e, com
 * `RAGX_PANEL_METRICS_PLAN="visible:5,minimized:5,hidden:5"`, leva a janela a cada estado pelo tempo
 * pedido e encerra o app. Sem a variável nada disso existe. Nenhum canal IPC novo.
 */
function startRuntimeMeasurement(): void {
  if (METRICS_FILE === null || HEADLESS) return
  fs.mkdirSync(path.dirname(METRICS_FILE), { recursive: true })
  const sampler = createRuntimeSampler({
    getAppMetrics: () => app.getAppMetrics(),
    getState: () => panelState,
    getSnapshotMs: () => lastSnapshotMs,
    write: (line) => fs.appendFileSync(METRICS_FILE, line + '\n'),
  })
  sampler.start()

  const planText = process.env.RAGX_PANEL_METRICS_PLAN?.trim()
  if (!planText) return
  const steps = parsePlan(planText)
  void (async () => {
    for (const step of steps) {
      const win = mainWindow
      if (win === null) break
      if (step.state === 'visible') {
        win.show()
        win.restore()
      } else if (step.state === 'minimized') {
        win.minimize()
      } else {
        win.hide()
      }
      panelState = step.state
      await new Promise((resolve) => setTimeout(resolve, step.minutes * 60_000))
    }
    sampler.stop()
    app.quit()
  })()
}

// -- janela ------------------------------------------------------------

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'RAGX Painel',
    // Empacotado, a janela herda o ícone do .exe (gravado no afterPack); em
    // dev o processo é o electron.exe, então o ícone vem do arquivo.
    ...(isDev ? { icon: path.join(__dirname, '..', 'build', 'icon.ico') } : {}),
    autoHideMenuBar: true,
    backgroundColor: '#000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // RAGX-0171: o Chromium reduz o trabalho do renderer com a janela fora da vista (explícito, não o padrão implícito)
      backgroundThrottling: true,
    },
  })
  mainWindow = win

  // Fix round 1 (MINOR 6): a janela nunca navega pra fora do próprio app -
  // um link externo ou uma navegação injetada não troca o conteúdo carregado
  // por uma página arbitrária (fora da URL do servidor de dev, em `isDev`).
  win.webContents.on('will-navigate', (event, url) => {
    if (isDev && isDevServerUrl(url)) return
    event.preventDefault()
  })
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))

  if (isDev) {
    win.loadURL(DEV_SERVER_URL)
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  win.webContents.once('did-finish-load', () => {
    startSnapshotPolling()
    startConnectionsPolling()
    startActivityPolling()
    watchPanelActivity(win)
    startRuntimeMeasurement()
    // Fix round 1 (MINOR 4): a primeira checagem de conexão roda logo depois
    // do primeiro snapshot, sem esperar os 30s do polling - `getConnections`
    // já constrói um snapshot se ainda não houver nenhum (decisão 2 da Task 6).
    handlers.getConnections().catch((err) => console.error('getConnections() falhou no startup:', err))
    // Painel aberto sem a CLI (o bootstrap do instalador falhou ou nunca rodou): tenta de novo
    // já com a barra de progresso na tela. Sem pacote no `.exe` (dev), não faz nada.
    if (resolveRagx() === null && findBundleDir() !== null) enqueueRagxInstall()
  })

  win.on('close', (e) => {
    if (!queue.hasActive()) return
    const choice = dialog.showMessageBoxSync(win, {
      message: 'Há tarefas em andamento. Fechar o painel cancela todas.',
      buttons: ['Continuar no painel', 'Fechar e cancelar'],
      cancelId: 0,
      defaultId: 0,
    })
    if (choice !== 1) {
      e.preventDefault()
      return
    }
    for (const job of queue.list()) {
      if (job.state === 'queued' || job.state === 'running') queue.cancel(job.id)
    }
  })

  win.on('closed', () => {
    stopWatchingActivity?.()
    stopWatchingActivity = null
    snapshotPoller?.stop()
    connectionsPoller?.stop()
    activityPoller?.stop()
    snapshotPoller = null
    connectionsPoller = null
    activityPoller = null
    mainWindow = null
  })
}

/** Uma segunda abertura do painel foca a janela que já existe (RAGX-0171). */
function focusExistingWindow(): void {
  const win = mainWindow
  if (win === null) return
  if (win.isMinimized()) win.restore()
  win.show()
  win.focus()
}

// Os modos `--bootstrap` e `--uninstall-cli` do instalador NÃO pegam a trava; `RAGX_PANEL_ALLOW_MULTI=1` a desliga.
const GOT_SINGLE_INSTANCE = acquireSingleInstance(app, {
  headless: HEADLESS,
  allowMulti: process.env.RAGX_PANEL_ALLOW_MULTI === '1',
  onSecondInstance: focusExistingWindow,
})

app.whenReady().then(async () => {
  if (!GOT_SINGLE_INSTANCE) return
  // sql.js carrega seu modulo WASM de forma assincrona; precisa terminar
  // antes de qualquer chamada a readProjectStats (via buildSnapshot), que
  // acontece a partir do polling ou do handler ragx:getSnapshot — ambos
  // disparados so depois que a janela carrega (ver Ruling D, Task 2).
  await initSqlWasm().catch((err) => {
    console.error('initSqlWasm falhou; stats de projetos ficarão indisponíveis:', err)
  })

  if (HEADLESS) {
    const code = BOOTSTRAP ? await runBootstrapHeadless() : await runUninstallHeadless()
    app.exit(code)
    return
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

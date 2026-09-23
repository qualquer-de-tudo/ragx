import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { initSqlWasm } from './data/project-stats'
import { buildSnapshot } from './data/snapshot'
import { runRagxCommand } from './data/run-ragx-command'
import { checkAll, defaultCheckDeps } from './connections/checks'
import { resetRagxCache } from './system/ragx-exe'
import { JobQueue, defaultSpawn } from './jobs/queue'
import { FolderTokens } from './projects/tokens'
import { discoverProjects } from './projects/discovery'
import { readSettings, writeSettings } from './settings'
import { createHandlers } from './ipc'
import type { ConnectionCheck, JobView, Snapshot } from '../src/types/ragx-bridge'

const isDev = !app.isPackaged

const SNAPSHOT_POLL_MS = 5000
const CONNECTIONS_POLL_MS = 30_000
const JOBS_THROTTLE_MS = 250

let mainWindow: BrowserWindow | null = null
let snapshotTimer: ReturnType<typeof setInterval> | null = null
let connectionsTimer: ReturnType<typeof setInterval> | null = null
let connectionsInFlight = false

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

function refreshSnapshot(): Promise<Snapshot> {
  if (inFlightSnapshot) return inFlightSnapshot
  const promise = (async () => {
    try {
      const s = await buildSnapshot()
      latestSnapshot = s
      return withConnectionsHealth(s)
    } finally {
      inFlightSnapshot = null
    }
  })()
  inFlightSnapshot = promise
  return promise
}

// -- fila de tarefas ---------------------------------------------------

const queue = new JobQueue({ spawn: defaultSpawn(), now: () => Date.now(), newId: () => randomUUID() }, (jobs) =>
  onJobsChange(jobs),
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
  const TERMINAL: ReadonlySet<JobView['state']> = new Set(['done', 'failed', 'cancelled'])
  const justFinished = jobs.some((j) => {
    const prev = previousJobStates.get(j.id)
    return prev !== undefined && prev !== j.state && TERMINAL.has(j.state)
  })
  previousJobStates = new Map(jobs.map((j) => [j.id, j.state]))

  sendJobsThrottled(jobs)

  // Uma tarefa terminou: o renderer precisa ver o snapshot atualizado sem
  // esperar até 5s pelo próximo tick do polling. Se já tem uma reconstrução
  // rodando, não dispara outra em paralelo - marca "dirty" pra rodar mais
  // uma assim que essa terminar, porque ela pode ter começado antes da
  // tarefa terminar de verdade e não refletir o resultado final (MINOR 2).
  if (justFinished) pushSnapshotNow({ markDirtyIfBusy: true })
}

let snapshotDirtyAfterInFlight = false

function pushSnapshotNow(opts: { markDirtyIfBusy?: boolean } = {}): void {
  if (inFlightSnapshot) {
    if (opts.markDirtyIfBusy) snapshotDirtyAfterInFlight = true
    return // já tem uma reconstrução em andamento - a batida de polling/o "dirty" acima cobre isso
  }
  refreshSnapshot()
    .then((snapshot) => {
      mainWindow?.webContents.send('ragx:snapshot', snapshot)
      if (snapshotDirtyAfterInFlight) {
        snapshotDirtyAfterInFlight = false
        pushSnapshotNow()
      }
    })
    .catch((err) => console.error('buildSnapshot() falhou apos tarefa terminar:', err))
}

// -- handlers de IPC -----------------------------------------------------

const handlers = createHandlers({
  buildSnapshot: refreshSnapshot,
  getCachedSnapshot: () => (latestSnapshot ? withConnectionsHealth(latestSnapshot) : null),
  runRagxCommand,
  checkAll: async (snapshot) => {
    const checks = await checkAll(defaultCheckDeps(), snapshot)
    latestConnections = checks
    return checks
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
  readSettings: () => readSettings(app.getPath('userData')),
  writeSettings: (s) => writeSettings(app.getPath('userData'), s),
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
handleIpc('ragx:getProjectStatus', (projectId: unknown) => handlers.getProjectStatus(projectId))
handleIpc('ragx:runTrial', (projectId: unknown) => handlers.runTrial(projectId))
handleIpc('ragx:runSecurityScan', (projectId: unknown) => handlers.runSecurityScan(projectId))
handleIpc('ragx:getConnections', () => handlers.getConnections())
handleIpc('ragx:listJobs', () => handlers.listJobs())
handleIpc('ragx:enqueueJob', (req: unknown) => handlers.enqueueJob(req))
handleIpc('ragx:cancelJob', (jobId: unknown) => handlers.cancelJob(jobId))
handleIpc('ragx:pickFolder', () => handlers.pickFolder())
handleIpc('ragx:discover', (token: unknown) => handlers.discover(token))
handleIpc('ragx:getSettings', () => handlers.getSettings())
handleIpc('ragx:setOnboardingDone', (done: unknown) => handlers.setOnboardingDone(done))

// -- polling ---------------------------------------------------------------

function startSnapshotPolling(): void {
  if (snapshotTimer) return
  // git pode ser lento - `pushSnapshotNow` já pula a batida se a anterior
  // ainda não terminou, para nunca rodar `git` em paralelo para o mesmo projeto.
  snapshotTimer = setInterval(pushSnapshotNow, SNAPSHOT_POLL_MS)
}

function startConnectionsPolling(): void {
  if (connectionsTimer) return
  connectionsTimer = setInterval(() => {
    if (connectionsInFlight) return
    connectionsInFlight = true
    handlers
      .getConnections()
      .catch((err) => console.error('getConnections() falhou no polling:', err))
      .finally(() => {
        connectionsInFlight = false
      })
  }, CONNECTIONS_POLL_MS)
}

// -- janela ------------------------------------------------------------

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'RAGX Painel',
    autoHideMenuBar: true,
    backgroundColor: '#000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  mainWindow = win

  // Fix round 1 (MINOR 6): a janela nunca navega pra fora do próprio app -
  // um link externo ou uma navegação injetada não troca o conteúdo carregado
  // por uma página arbitrária (fora da URL do servidor de dev, em `isDev`).
  win.webContents.on('will-navigate', (event, url) => {
    if (isDev && url.startsWith('http://localhost:5173')) return
    event.preventDefault()
  })
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))

  if (isDev) {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  win.webContents.once('did-finish-load', () => {
    startSnapshotPolling()
    startConnectionsPolling()
    // Fix round 1 (MINOR 4): a primeira checagem de conexão roda logo depois
    // do primeiro snapshot, sem esperar os 30s do polling - `getConnections`
    // já constrói um snapshot se ainda não houver nenhum (decisão 2 da Task 6).
    handlers.getConnections().catch((err) => console.error('getConnections() falhou no startup:', err))
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
    if (snapshotTimer) clearInterval(snapshotTimer)
    if (connectionsTimer) clearInterval(connectionsTimer)
    snapshotTimer = null
    connectionsTimer = null
    mainWindow = null
  })
}

app.whenReady().then(async () => {
  // sql.js carrega seu modulo WASM de forma assincrona; precisa terminar
  // antes de qualquer chamada a readProjectStats (via buildSnapshot), que
  // acontece a partir do polling ou do handler ragx:getSnapshot — ambos
  // disparados so depois que a janela carrega (ver Ruling D, Task 2).
  await initSqlWasm().catch((err) => {
    console.error('initSqlWasm falhou — stats de projetos ficarão indisponíveis:', err)
  })

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

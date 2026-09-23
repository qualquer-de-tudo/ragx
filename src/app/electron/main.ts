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
let snapshotInFlight = false
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

async function refreshSnapshot(): Promise<Snapshot> {
  const s = await buildSnapshot()
  latestSnapshot = s
  return withConnectionsHealth(s)
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

  if (justFinished) pushSnapshotNow()
}

function pushSnapshotNow(): void {
  if (snapshotInFlight) return // já tem uma reconstrução em andamento - a próxima batida do polling cobre isso
  snapshotInFlight = true
  refreshSnapshot()
    .then((snapshot) => mainWindow?.webContents.send('ragx:snapshot', snapshot))
    .catch((err) => console.error('buildSnapshot() falhou apos tarefa terminar:', err))
    .finally(() => {
      snapshotInFlight = false
    })
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

ipcMain.handle('ragx:getSnapshot', () => handlers.getSnapshot())
ipcMain.handle('ragx:getProjectStatus', (_e, projectId: unknown) => handlers.getProjectStatus(projectId))
ipcMain.handle('ragx:runTrial', (_e, projectId: unknown) => handlers.runTrial(projectId))
ipcMain.handle('ragx:runSecurityScan', (_e, projectId: unknown) => handlers.runSecurityScan(projectId))
ipcMain.handle('ragx:getConnections', () => handlers.getConnections())
ipcMain.handle('ragx:listJobs', () => handlers.listJobs())
ipcMain.handle('ragx:enqueueJob', (_e, req: unknown) => handlers.enqueueJob(req))
ipcMain.handle('ragx:cancelJob', (_e, jobId: unknown) => handlers.cancelJob(jobId))
ipcMain.handle('ragx:pickFolder', () => handlers.pickFolder())
ipcMain.handle('ragx:discover', (_e, token: unknown) => handlers.discover(token))
ipcMain.handle('ragx:getSettings', () => handlers.getSettings())
ipcMain.handle('ragx:setOnboardingDone', (_e, done: unknown) => handlers.setOnboardingDone(done))

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

  if (isDev) {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  win.webContents.once('did-finish-load', () => {
    startSnapshotPolling()
    startConnectionsPolling()
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

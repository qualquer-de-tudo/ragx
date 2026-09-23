import { app, BrowserWindow, ipcMain } from 'electron'
import path from 'node:path'
import { readHubRegistry } from './data/hub'
import { initSqlWasm, readProjectStats } from './data/project-stats'
import { readTelemetry } from './data/telemetry'
import { runRagxCommand } from './data/run-ragx-command'
import type { Snapshot } from '../src/types/ragx-bridge'

const isDev = !app.isPackaged

const POLL_INTERVAL_MS = 5000
const TELEMETRY_WINDOW_HOURS = 24

// Cache do ultimo snapshot valido - usado como fallback se readHubRegistry()
// em si falhar (ex.: registry.json corrompido/truncado por escrita
// concorrente), para nao propagar um erro nao tratado ate o poll timer ou o
// handler IPC (ver Finding 2 da revisao final).
let lastGoodSnapshot: Snapshot | null = null

function buildSnapshot(): Snapshot {
  let registry: ReturnType<typeof readHubRegistry>
  try {
    registry = readHubRegistry()
  } catch (err) {
    console.error('readHubRegistry() falhou - registry.json pode estar corrompido/em escrita:', err)
    // Sem dado por projeto para isolar aqui - devolve o ultimo snapshot bom
    // conhecido (se houver) em vez de deixar o erro propagar e derrubar o
    // painel inteiro.
    return lastGoodSnapshot ?? { projects: [], generatedAt: new Date().toISOString() }
  }

  const projects = registry.map((proj) => {
    let stats: Snapshot['projects'][number]['stats']
    try {
      stats = proj.path
        ? readProjectStats(proj.path)
        : { unavailable: true as const, reason: 'projeto sem caminho local (só federação)' }
    } catch (err) {
      console.error(`readProjectStats falhou para o projeto "${proj.name}":`, err)
      stats = { unavailable: true as const, reason: 'falha ao ler estatísticas do projeto' }
    }

    let telemetry: Snapshot['projects'][number]['telemetry']
    try {
      telemetry = proj.path
        ? readTelemetry(proj.path, TELEMETRY_WINDOW_HOURS)
        : { callsByTool: [], totalCalls: 0, tokensDelivered: 0 }
    } catch (err) {
      console.error(`readTelemetry falhou para o projeto "${proj.name}":`, err)
      telemetry = { callsByTool: [], totalCalls: 0, tokensDelivered: 0 }
    }

    return { ...proj, stats, telemetry }
  })

  const snapshot = { projects, generatedAt: new Date().toISOString() }
  lastGoodSnapshot = snapshot
  return snapshot
}

let mainWindow: BrowserWindow | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    mainWindow?.webContents.send('ragx:snapshot', buildSnapshot())
  }, POLL_INTERVAL_MS)
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1100,
    height: 720,
    title: 'RAGX — Painel',
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

  win.webContents.once('did-finish-load', startPolling)
  win.on('closed', () => {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
    mainWindow = null
  })
}

ipcMain.handle('ragx:get-snapshot', () => buildSnapshot())
ipcMain.handle('ragx:run-trial', (_event, projectPath: string) =>
  runRagxCommand(projectPath, ['trial', '--json']),
)
ipcMain.handle('ragx:run-security-scan', (_event, projectPath: string) =>
  runRagxCommand(projectPath, ['security', 'scan', '.', '--json']),
)

app.whenReady().then(async () => {
  // sql.js carrega seu modulo WASM de forma assincrona; precisa terminar
  // antes de qualquer chamada a readProjectStats (via buildSnapshot), que
  // acontece a partir de startPolling() ou do handler ragx:get-snapshot —
  // ambos disparados so depois que a janela carrega (ver Ruling D, Task 2).
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

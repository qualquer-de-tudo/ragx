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

function buildSnapshot(): Snapshot {
  const projects = readHubRegistry().map((proj) => ({
    ...proj,
    stats: proj.path
      ? readProjectStats(proj.path)
      : { unavailable: true as const, reason: 'projeto sem caminho local (só federação)' },
    telemetry: proj.path ? readTelemetry(proj.path, TELEMETRY_WINDOW_HOURS) : { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
  }))
  return { projects, generatedAt: new Date().toISOString() }
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
  await initSqlWasm()

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

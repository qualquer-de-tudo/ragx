import { app, BrowserWindow, ipcMain, nativeTheme } from 'electron'
import path from 'node:path'
import { initSqlWasm } from './data/project-stats'
import { buildSnapshot } from './data/snapshot'
import { runRagxCommand } from './data/run-ragx-command'

const isDev = !app.isPackaged

const POLL_INTERVAL_MS = 5000

let mainWindow: BrowserWindow | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    buildSnapshot()
      .then((snapshot) => mainWindow?.webContents.send('ragx:snapshot', snapshot))
      .catch((err) => console.error('buildSnapshot() falhou no polling:', err))
  }, POLL_INTERVAL_MS)
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'RAGX — Painel',
    autoHideMenuBar: true,
    // Mesma cor do fundo da página: sem flash branco antes do React montar.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#131b24' : '#f8fafc',
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

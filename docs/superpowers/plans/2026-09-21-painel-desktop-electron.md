# Painel Desktop Electron Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows `.exe` desktop app (Electron + React, in the existing `src/app/` scaffold) that opens with no login and shows, per RAGX project known to the local hub: document/chunk/embedding counts, MCP call counts and tokens delivered (from `.ragx/logs/mcp.jsonl`, produced by the telemetria-mcp plan), and the last security scan's findings — refreshed by simple polling.

**Architecture:** Electron's main process (Node, filesystem access) reads three already-existing local sources — `~/.ragx/hub/registry.json`, each project's `.ragx/knowledge.db` (via `better-sqlite3`), and `.ragx/logs/mcp.jsonl` — on a timer, and pushes the result to the renderer (React) over IPC. The renderer never touches the filesystem directly (`contextIsolation: true`, no `nodeIntegration`) — it only calls a typed bridge exposed by a preload script. Security scan results are fetched on demand (spawning `ragx security scan . --json` as a child process), not polled continuously, since it's comparatively expensive.

**Tech Stack:** Electron, React 19 (already in `src/app/package.json`), TypeScript, Vite (already configured), `better-sqlite3` (synchronous SQLite reads), `electron-builder` (packaging).

**Spec:** `docs/superpowers/specs/2026-09-21-painel-desktop-design.md`, section "Parte 2 — App Electron".
**Depends on:** `docs/superpowers/plans/2026-09-21-telemetria-mcp.md` (produces `.ragx/logs/mcp.jsonl` and hub auto-registration — this plan can be built and tested against a project that was registered manually with `ragx project register` even before that plan lands, but the telemetry data source (Task 3 below) won't have real data until it does).

## Global Constraints

- No login, no configuration screen on first run (spec: "Sem login, sem configuração na primeira tela").
- Renderer process has no direct filesystem or `child_process` access — everything goes through `ipcMain.handle`/`contextBridge` (Electron security baseline; not explicitly in the spec's prose but implied by "processo principal... lê diretamente" vs. renderer never mentioned touching files).
- Polling only, no file-watcher, in this version (spec: explicit).
- "Tokens economizados" (the `ragx trial` proxy number) is NEVER shown without a visible "estimativa" label, and never merged into the same number as "tokens entregues" (spec: "Por que tokens economizados não é um número real").
- One screen, two columns — no additional screens/routes in this version (spec: "Uma tela só, duas colunas").

---

### Task 1: Electron shell — window opens, shows the existing React app

**Files:**
- Modify: `src/app/package.json` (add `electron`, `electron-builder`, `concurrently`, `wait-on`, `cross-env` devDependencies; add `main` field; add `dev:electron`/`build:electron` scripts)
- Create: `src/app/electron/main.ts`
- Create: `src/app/electron/preload.ts`
- Create: `src/app/tsconfig.electron.json`
- Modify: `src/app/vite.config.ts` (set `base: './'` for correct asset paths when loaded via `file://` in production)

**Interfaces:**
- Produces: a `BrowserWindow` loading `http://localhost:5173` in dev (Vite dev server) or `dist/index.html` in production. No app-specific IPC yet — that's Task 2. Later tasks import nothing from this task's files except relying on the window existing and `preload.ts` being the place IPC bridges get added.

- [ ] **Step 1: Add dependencies**

From `src/app/`, run:

```bash
npm install --save-dev electron@^33 electron-builder@^25 concurrently@^9 wait-on@^8 cross-env@^7 tsx@^4
npm install better-sqlite3@^11
npm install --save-dev @types/better-sqlite3@^7
```

- [ ] **Step 2: Create the Electron main process entry**

Create `src/app/electron/main.ts`:

```typescript
import { app, BrowserWindow } from 'electron'
import path from 'node:path'

const isDev = !app.isPackaged

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

  if (isDev) {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
```

- [ ] **Step 3: Create the preload script (empty bridge for now)**

Create `src/app/electron/preload.ts`:

```typescript
import { contextBridge } from 'electron'

// A ponte real (leitura de projetos/telemetria) entra na Task 2. Por ora,
// so confirma que o preload carregou, pra Task 1 validar a integracao.
contextBridge.exposeInMainWorld('ragx', {
  ping: () => 'pong',
})
```

- [ ] **Step 4: Add a TypeScript config for the Electron files**

Create `src/app/tsconfig.electron.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "CommonJS",
    "moduleResolution": "Node",
    "outDir": "dist-electron",
    "rootDir": "electron",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["electron/**/*.ts"]
}
```

- [ ] **Step 5: Wire up `package.json` scripts**

Read the current `src/app/package.json` first (it was scaffolded by `npm create vite`, so it only has `dev`/`build`/`lint`/`preview` — add to that, don't replace it). Add:

```json
{
  "main": "dist-electron/main.js",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview",
    "build:electron:ts": "tsc -p tsconfig.electron.json",
    "dev:electron": "concurrently -k \"npm:dev\" \"npm run build:electron:ts -- --watch\" \"wait-on tcp:5173 && cross-env NODE_ENV=development electron dist-electron/main.js\"",
    "package": "npm run build && npm run build:electron:ts && electron-builder"
  }
}
```

- [ ] **Step 6: Set the Vite base path for production loads**

In `src/app/vite.config.ts`, read the current content first, then add
`base: './'` to the `defineConfig({...})` call — without it, the packaged
app's `index.html` references `/assets/...` (absolute), which fails under
`file://`.

- [ ] **Step 7: Verify the window opens and shows the existing scaffold**

Run (from `src/app/`): `npm run dev:electron`
Expected: an Electron window opens showing the default Vite+React counter
page (the one already in `App.tsx`) — no crash, no blank window. Close the
window/process before continuing (Ctrl+C in the terminal).

- [ ] **Step 8: Commit**

```bash
git add src/app/package.json src/app/package-lock.json src/app/electron/ src/app/tsconfig.electron.json src/app/vite.config.ts
git commit -m "feat(app): esqueleto Electron abrindo o scaffold React existente"
```

---

### Task 2: Leitura de dados no processo principal — hub, knowledge.db, mcp.jsonl

**Files:**
- Create: `src/app/electron/data/hub.ts`
- Create: `src/app/electron/data/project-stats.ts`
- Create: `src/app/electron/data/telemetry.ts`
- Create: `src/app/electron/data/types.ts`
- Test: `src/app/electron/data/__tests__/hub.test.ts`, `src/app/electron/data/__tests__/telemetry.test.ts`
- Modify: `src/app/package.json` (add `vitest` devDependency + `test` script, if not already added by the existing scaffold — check first, the default `npm create vite -- --template react-ts` does NOT include a test runner)

**Interfaces:**
- Produces:
  - `HubProject` type and `readHubRegistry(): HubProject[]` (`hub.ts`) — reads `~/.ragx/hub/registry.json`, returns `[]` if the file doesn't exist (empty hub, not an error).
  - `ProjectStats` type and `readProjectStats(projectPath: string): ProjectStats | { unavailable: true; reason: string }` (`project-stats.ts`) — opens `<projectPath>/.ragx/knowledge.db` read-only via `better-sqlite3`.
  - `TelemetrySummary` type and `readTelemetry(projectPath: string, sinceHours: number): TelemetrySummary` (`telemetry.ts`) — reads and aggregates `<projectPath>/.ragx/logs/mcp.jsonl`, returns zeroed summary if the file doesn't exist.
  - All three consumed by Task 3 (IPC handlers) and Task 4 (renderer, via IPC — never imports these files directly).

- [ ] **Step 1: Add a test runner**

Check `src/app/package.json` for an existing `vitest` devDependency first
(the plain `react-ts` Vite template does not include one). If absent:

```bash
cd src/app && npm install --save-dev vitest@^2
```

Add to `package.json`'s `scripts`: `"test": "vitest run"`.

- [ ] **Step 2: Define shared types**

Create `src/app/electron/data/types.ts`:

```typescript
export interface HubProject {
  id: string
  name: string
  path: string | null
  cloned: boolean
  embeddingModel: string | null
  visibility: string
  status: string
  chunks: number
  lastSync: string | null
}

export interface ProjectStats {
  documents: number
  chunks: number
  embeddings: number
}

export interface ProjectStatsUnavailable {
  unavailable: true
  reason: string
}

export interface TelemetryCallCount {
  tool: string
  count: number
}

export interface TelemetrySummary {
  callsByTool: TelemetryCallCount[]
  totalCalls: number
  tokensDelivered: number
}
```

- [ ] **Step 3: Write the failing test for `readHubRegistry`**

Create `src/app/electron/data/__tests__/hub.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

vi.mock('node:os', async (importOriginal) => {
  const actual = await importOriginal<typeof os>()
  return { ...actual, homedir: vi.fn() }
})

describe('readHubRegistry', () => {
  let tmpHome: string

  beforeEach(() => {
    tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-hub-test-'))
    vi.mocked(os.homedir).mockReturnValue(tmpHome)
  })

  it('retorna lista vazia quando o hub nao existe', async () => {
    const { readHubRegistry } = await import('../hub')
    expect(readHubRegistry()).toEqual([])
  })

  it('le e mapeia o registry.json existente', async () => {
    const hubDir = path.join(tmpHome, '.ragx', 'hub')
    fs.mkdirSync(hubDir, { recursive: true })
    fs.writeFileSync(
      path.join(hubDir, 'registry.json'),
      JSON.stringify({
        schema_version: 1,
        projects: [
          {
            id: 'abc123',
            name: 'meu-projeto',
            path: 'C:\\projects\\meu-projeto',
            cloned: 1,
            embedding_model: 'fastembed:x',
            visibility: 'workspace',
            status: 'ok',
            chunks: 42,
            last_sync: '2026-09-21T10:00:00Z',
          },
        ],
      }),
      'utf-8',
    )

    const { readHubRegistry } = await import('../hub')
    const result = readHubRegistry()
    expect(result).toEqual([
      {
        id: 'abc123',
        name: 'meu-projeto',
        path: 'C:\\projects\\meu-projeto',
        cloned: true,
        embeddingModel: 'fastembed:x',
        visibility: 'workspace',
        status: 'ok',
        chunks: 42,
        lastSync: '2026-09-21T10:00:00Z',
      },
    ])
  })
})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd src/app && npx vitest run electron/data/__tests__/hub.test.ts`
Expected: FAIL — `Cannot find module '../hub'`

- [ ] **Step 5: Implement `hub.ts`**

Create `src/app/electron/data/hub.ts`:

```typescript
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { HubProject } from './types'

interface RawRegistry {
  schema_version: number
  projects: Array<{
    id: string
    name: string
    path: string | null
    cloned: number
    embedding_model: string | null
    visibility: string
    status: string
    chunks: number
    last_sync: string | null
  }>
}

function registryPath(): string {
  return path.join(os.homedir(), '.ragx', 'hub', 'registry.json')
}

export function readHubRegistry(): HubProject[] {
  const p = registryPath()
  if (!fs.existsSync(p)) return []

  const raw: RawRegistry = JSON.parse(fs.readFileSync(p, 'utf-8'))
  return raw.projects.map((proj) => ({
    id: proj.id,
    name: proj.name,
    path: proj.path,
    cloned: Boolean(proj.cloned),
    embeddingModel: proj.embedding_model,
    visibility: proj.visibility,
    status: proj.status,
    chunks: proj.chunks,
    lastSync: proj.last_sync,
  }))
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd src/app && npx vitest run electron/data/__tests__/hub.test.ts`
Expected: 2 passed

- [ ] **Step 7: Implement `project-stats.ts` (no test — thin wrapper over `better-sqlite3`, exercised end-to-end in Task 5)**

Create `src/app/electron/data/project-stats.ts`:

```typescript
import fs from 'node:fs'
import path from 'node:path'
import Database from 'better-sqlite3'
import type { ProjectStats, ProjectStatsUnavailable } from './types'

export function readProjectStats(
  projectPath: string,
): ProjectStats | ProjectStatsUnavailable {
  if (!fs.existsSync(projectPath)) {
    return { unavailable: true, reason: 'pasta do projeto não existe mais' }
  }
  const dbPath = path.join(projectPath, '.ragx', 'knowledge.db')
  if (!fs.existsSync(dbPath)) {
    return { unavailable: true, reason: 'projeto ainda não foi indexado (.ragx/knowledge.db ausente)' }
  }

  const db = new Database(dbPath, { readonly: true, fileMustExist: true })
  try {
    const documents = (db.prepare('SELECT COUNT(*) AS n FROM documents').get() as { n: number }).n
    const chunks = (db.prepare('SELECT COUNT(*) AS n FROM chunks').get() as { n: number }).n
    const embeddings = (db.prepare('SELECT COUNT(*) AS n FROM embeddings').get() as { n: number }).n
    return { documents, chunks, embeddings }
  } finally {
    db.close()
  }
}
```

- [ ] **Step 8: Write the failing test for `readTelemetry`**

Create `src/app/electron/data/__tests__/telemetry.test.ts`:

```typescript
import { describe, expect, it, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { readTelemetry } from '../telemetry'

describe('readTelemetry', () => {
  let projectPath: string

  beforeEach(() => {
    projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-telemetry-test-'))
  })

  it('devolve zerado quando mcp.jsonl nao existe', () => {
    const result = readTelemetry(projectPath, 24)
    expect(result).toEqual({ callsByTool: [], totalCalls: 0, tokensDelivered: 0 })
  })

  it('agrega chamadas por ferramenta e soma tokens_delivered', () => {
    const logDir = path.join(projectPath, '.ragx', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const now = new Date().toISOString()
    const lines = [
      { ts: now, tool: 'search_hybrid', ms: 10, project: 't' },
      { ts: now, tool: 'search_hybrid', ms: 12, project: 't' },
      { ts: now, tool: 'build_context', ms: 30, project: 't', tokens_delivered: 500 },
      { ts: now, tool: 'build_context', ms: 28, project: 't', tokens_delivered: 300 },
    ]
    fs.writeFileSync(
      path.join(logDir, 'mcp.jsonl'),
      lines.map((l) => JSON.stringify(l)).join('\n') + '\n',
      'utf-8',
    )

    const result = readTelemetry(projectPath, 24)
    expect(result.totalCalls).toBe(4)
    expect(result.tokensDelivered).toBe(800)
    expect(result.callsByTool).toEqual(
      expect.arrayContaining([
        { tool: 'search_hybrid', count: 2 },
        { tool: 'build_context', count: 2 },
      ]),
    )
  })

  it('ignora linhas mais antigas que sinceHours', () => {
    const logDir = path.join(projectPath, '.ragx', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const old = new Date(Date.now() - 48 * 3600 * 1000).toISOString()
    const recent = new Date().toISOString()
    const lines = [
      { ts: old, tool: 'search_hybrid', ms: 10, project: 't' },
      { ts: recent, tool: 'search_hybrid', ms: 10, project: 't' },
    ]
    fs.writeFileSync(
      path.join(logDir, 'mcp.jsonl'),
      lines.map((l) => JSON.stringify(l)).join('\n') + '\n',
      'utf-8',
    )

    const result = readTelemetry(projectPath, 24)
    expect(result.totalCalls).toBe(1)
  })
})
```

- [ ] **Step 9: Run test to verify it fails**

Run: `cd src/app && npx vitest run electron/data/__tests__/telemetry.test.ts`
Expected: FAIL — `Cannot find module '../telemetry'`

- [ ] **Step 10: Implement `telemetry.ts`**

Create `src/app/electron/data/telemetry.ts`:

```typescript
import fs from 'node:fs'
import path from 'node:path'
import type { TelemetrySummary } from './types'

interface LogLine {
  ts: string
  tool: string
  ms: number
  project: string
  tokens_delivered?: number
}

export function readTelemetry(projectPath: string, sinceHours: number): TelemetrySummary {
  const logPath = path.join(projectPath, '.ragx', 'logs', 'mcp.jsonl')
  if (!fs.existsSync(logPath)) {
    return { callsByTool: [], totalCalls: 0, tokensDelivered: 0 }
  }

  const cutoff = Date.now() - sinceHours * 3600 * 1000
  const byTool = new Map<string, number>()
  let tokensDelivered = 0
  let totalCalls = 0

  const raw = fs.readFileSync(logPath, 'utf-8')
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue
    let entry: LogLine
    try {
      entry = JSON.parse(line)
    } catch {
      continue // linha corrompida (escrita concorrente truncada) - ignora, nao quebra o painel
    }
    if (new Date(entry.ts).getTime() < cutoff) continue

    totalCalls += 1
    byTool.set(entry.tool, (byTool.get(entry.tool) ?? 0) + 1)
    if (typeof entry.tokens_delivered === 'number') {
      tokensDelivered += entry.tokens_delivered
    }
  }

  return {
    callsByTool: [...byTool.entries()].map(([tool, count]) => ({ tool, count })),
    totalCalls,
    tokensDelivered,
  }
}
```

- [ ] **Step 11: Run test to verify it passes**

Run: `cd src/app && npx vitest run electron/data/__tests__/telemetry.test.ts`
Expected: 3 passed

- [ ] **Step 12: Run the full frontend test suite**

Run: `cd src/app && npm test`
Expected: 5 passed (2 hub + 3 telemetry)

- [ ] **Step 13: Commit**

```bash
git add src/app/package.json src/app/package-lock.json src/app/electron/data/
git commit -m "feat(app): leitura de hub, knowledge.db e mcp.jsonl no processo principal"
```

---

### Task 3: IPC — expor os dados pro renderer, com polling

**Files:**
- Modify: `src/app/electron/main.ts` (add `ipcMain.handle` calls and the polling timer)
- Modify: `src/app/electron/preload.ts` (replace the placeholder bridge with the real one)
- Create: `src/app/src/types/ragx-bridge.d.ts` (ambient type for `window.ragx`, shared between preload and renderer)

**Interfaces:**
- Consumes: `readHubRegistry`, `readProjectStats`, `readTelemetry` from Task 2 (exact names/signatures as defined there).
- Produces: `window.ragx.getSnapshot(): Promise<Snapshot>` and `window.ragx.onSnapshot(cb: (s: Snapshot) => void): () => void` (the unsubscribe function it returns), where `Snapshot = { projects: Array<HubProject & { stats: ProjectStats | ProjectStatsUnavailable; telemetry: TelemetrySummary }> }`. Task 4 (React UI) consumes exactly this bridge — no other IPC channel is added in this plan.

- [ ] **Step 1: Define the shared snapshot type and update the preload's ambient declaration**

Create `src/app/src/types/ragx-bridge.d.ts`:

```typescript
import type { HubProject, ProjectStats, ProjectStatsUnavailable, TelemetrySummary } from '../../electron/data/types'

export interface ProjectSnapshot extends HubProject {
  stats: ProjectStats | ProjectStatsUnavailable
  telemetry: TelemetrySummary
}

export interface Snapshot {
  projects: ProjectSnapshot[]
  generatedAt: string
}

export interface RagxBridge {
  getSnapshot: () => Promise<Snapshot>
  onSnapshot: (cb: (snapshot: Snapshot) => void) => () => void
}

declare global {
  interface Window {
    ragx: RagxBridge
  }
}
```

- [ ] **Step 2: Build the snapshot function and wire polling in `main.ts`**

Modify `src/app/electron/main.ts` — add these imports at the top (alongside
the existing `app`/`BrowserWindow`/`path` imports):

```typescript
import { ipcMain } from 'electron'
import { readHubRegistry } from './data/hub'
import { readProjectStats } from './data/project-stats'
import { readTelemetry } from './data/telemetry'
import type { Snapshot } from '../src/types/ragx-bridge'
```

Add, before `createWindow()`'s definition:

```typescript
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
```

Modify `createWindow()` to assign `mainWindow` and start polling once the
page has loaded (read the existing function from Task 1 and adapt it —
don't duplicate the whole thing, just apply these two changes):

```typescript
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
```

Add the IPC handler, alongside `app.whenReady().then(...)` (before it, since
`ipcMain.handle` should be registered before any renderer can call it):

```typescript
ipcMain.handle('ragx:get-snapshot', () => buildSnapshot())
```

- [ ] **Step 3: Implement the real preload bridge**

Replace `src/app/electron/preload.ts` entirely:

```typescript
import { contextBridge, ipcRenderer } from 'electron'
import type { Snapshot } from '../src/types/ragx-bridge'

contextBridge.exposeInMainWorld('ragx', {
  getSnapshot: (): Promise<Snapshot> => ipcRenderer.invoke('ragx:get-snapshot'),
  onSnapshot: (cb: (snapshot: Snapshot) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, snapshot: Snapshot) => cb(snapshot)
    ipcRenderer.on('ragx:snapshot', listener)
    return () => ipcRenderer.removeListener('ragx:snapshot', listener)
  },
})
```

- [ ] **Step 4: Manual verification (no automated test for IPC plumbing itself — Task 4 covers the renderer side with a mocked bridge)**

Run: `cd src/app && npm run dev:electron`

Open DevTools (already auto-opened in dev per Task 1's `openDevTools` call)
and in the console run `await window.ragx.getSnapshot()` — expected: a
`Snapshot` object with `projects: []` if the hub is empty on this machine,
or real project entries if `ragx project register` has already been run for
at least one project. No thrown error either way.

- [ ] **Step 5: Commit**

```bash
git add src/app/electron/main.ts src/app/electron/preload.ts src/app/src/types/
git commit -m "feat(app): expoe snapshot de projetos via IPC, com polling a cada 5s"
```

---

### Task 4: UI React — lista de projetos + painel de detalhe

**Files:**
- Create: `src/app/src/hooks/useSnapshot.ts`
- Create: `src/app/src/components/ProjectList.tsx`
- Create: `src/app/src/components/ProjectDetail.tsx`
- Modify: `src/app/src/App.tsx` (replace the default Vite scaffold content entirely)
- Modify: `src/app/src/App.css` (replace the default styling — keep it minimal, no design system, per "simples e rápido")
- Test: `src/app/src/components/__tests__/ProjectList.test.tsx`, `src/app/src/hooks/__tests__/useSnapshot.test.ts`
- Modify: `src/app/package.json` (add `@testing-library/react@^16`, `@testing-library/jest-dom@^6`, `jsdom@^25` devDependencies; vitest needs a `jsdom` environment config for component tests — add `test: { environment: 'jsdom' }` to `vite.config.ts`, not `package.json`)

**Interfaces:**
- Consumes: `window.ragx.getSnapshot`/`window.ragx.onSnapshot` (Task 3's bridge, exact shape from `src/app/src/types/ragx-bridge.d.ts`).
- Produces: `App` renders `ProjectList` (left column) + `ProjectDetail` (right column) — this is the terminal UI component of this plan; no later task consumes anything from here.

- [ ] **Step 1: Add test dependencies and jsdom environment**

```bash
cd src/app && npm install --save-dev @testing-library/react@^16 @testing-library/jest-dom@^6 jsdom@^25
```

In `src/app/vite.config.ts`, add a `test` block to the `defineConfig` call
(read the current file first — it already has `plugins: [react()]` from
Task 1's edit; add alongside, don't replace):

```typescript
test: {
  environment: 'jsdom',
},
```

- [ ] **Step 2: Write the failing test for `useSnapshot`**

Create `src/app/src/hooks/__tests__/useSnapshot.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useSnapshot } from '../useSnapshot'
import type { Snapshot } from '../../types/ragx-bridge'

const emptySnapshot: Snapshot = { projects: [], generatedAt: '2026-09-21T10:00:00Z' }

describe('useSnapshot', () => {
  beforeEach(() => {
    const listeners: Array<(s: Snapshot) => void> = []
    // @ts-expect-error -- bridge de teste, tipagem completa nao importa aqui
    window.ragx = {
      getSnapshot: vi.fn().mockResolvedValue(emptySnapshot),
      onSnapshot: vi.fn((cb: (s: Snapshot) => void) => {
        listeners.push(cb)
        return () => {
          const i = listeners.indexOf(cb)
          if (i >= 0) listeners.splice(i, 1)
        }
      }),
    }
  })

  it('carrega o snapshot inicial via getSnapshot', async () => {
    const { result } = renderHook(() => useSnapshot())
    await waitFor(() => expect(result.current.snapshot).toEqual(emptySnapshot))
    expect(window.ragx.getSnapshot).toHaveBeenCalledOnce()
  })

  it('assina onSnapshot e desinscreve ao desmontar', async () => {
    const { unmount } = renderHook(() => useSnapshot())
    await waitFor(() => expect(window.ragx.onSnapshot).toHaveBeenCalledOnce())
    unmount()
    // a funcao de unsubscribe devolvida pelo mock deve ter sido chamada
    const onSnapshotMock = vi.mocked(window.ragx.onSnapshot)
    const unsubscribe = onSnapshotMock.mock.results[0]?.value
    expect(unsubscribe).toBeDefined()
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd src/app && npx vitest run src/hooks/__tests__/useSnapshot.test.ts`
Expected: FAIL — `Cannot find module '../useSnapshot'`

- [ ] **Step 4: Implement `useSnapshot`**

Create `src/app/src/hooks/useSnapshot.ts`:

```typescript
import { useEffect, useState } from 'react'
import type { Snapshot } from '../types/ragx-bridge'

export function useSnapshot(): { snapshot: Snapshot | null } {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)

  useEffect(() => {
    let cancelled = false
    window.ragx.getSnapshot().then((s) => {
      if (!cancelled) setSnapshot(s)
    })
    const unsubscribe = window.ragx.onSnapshot((s) => setSnapshot(s))
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  return { snapshot }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd src/app && npx vitest run src/hooks/__tests__/useSnapshot.test.ts`
Expected: 2 passed

- [ ] **Step 6: Write the failing test for `ProjectList`**

Create `src/app/src/components/__tests__/ProjectList.test.tsx`:

```typescript
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProjectList } from '../ProjectList'
import type { ProjectSnapshot } from '../../types/ragx-bridge'

const projects: ProjectSnapshot[] = [
  {
    id: '1', name: 'projeto-a', path: 'C:\\a', cloned: true, embeddingModel: 'x',
    visibility: 'workspace', status: 'ok', chunks: 10, lastSync: null,
    stats: { documents: 5, chunks: 10, embeddings: 10 },
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
  },
  {
    id: '2', name: 'projeto-b', path: 'C:\\b', cloned: true, embeddingModel: 'x',
    visibility: 'workspace', status: 'degraded', chunks: 3, lastSync: null,
    stats: { unavailable: true, reason: 'pasta não existe' },
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
  },
]

describe('ProjectList', () => {
  it('lista os nomes dos projetos e o status de cada um', () => {
    render(<ProjectList projects={projects} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText('projeto-a')).toBeInTheDocument()
    expect(screen.getByText('projeto-b')).toBeInTheDocument()
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('chama onSelect com o id do projeto clicado', () => {
    const onSelect = vi.fn()
    render(<ProjectList projects={projects} selectedId={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('projeto-b'))
    expect(onSelect).toHaveBeenCalledWith('2')
  })

  it('mostra mensagem quando a lista esta vazia', () => {
    render(<ProjectList projects={[]} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText(/nenhum projeto/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd src/app && npx vitest run src/components/__tests__/ProjectList.test.tsx`
Expected: FAIL — `Cannot find module '../ProjectList'`

- [ ] **Step 8: Implement `ProjectList`**

Create `src/app/src/components/ProjectList.tsx`:

```typescript
import type { ProjectSnapshot } from '../types/ragx-bridge'

interface Props {
  projects: ProjectSnapshot[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ProjectList({ projects, selectedId, onSelect }: Props) {
  if (projects.length === 0) {
    return (
      <aside className="project-list">
        <p className="empty-hint">
          Nenhum projeto no hub ainda. Rode <code>ragx project register &lt;caminho&gt;</code> num
          projeto já indexado.
        </p>
      </aside>
    )
  }

  return (
    <aside className="project-list">
      <ul>
        {projects.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className={p.id === selectedId ? 'selected' : ''}
              onClick={() => onSelect(p.id)}
            >
              <span className="name">{p.name}</span>
              <span className={`status status-${p.status}`}>{p.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd src/app && npx vitest run src/components/__tests__/ProjectList.test.tsx`
Expected: 3 passed

- [ ] **Step 10: Implement `ProjectDetail` (no separate test file — a thin presentational component; covered by the App-level manual check in Step 12)**

Create `src/app/src/components/ProjectDetail.tsx`:

```typescript
import type { ProjectSnapshot } from '../types/ragx-bridge'

interface Props {
  project: ProjectSnapshot | null
}

export function ProjectDetail({ project }: Props) {
  if (!project) {
    return <main className="project-detail"><p>Selecione um projeto à esquerda.</p></main>
  }

  const { stats, telemetry } = project

  return (
    <main className="project-detail">
      <h1>{project.name}</h1>
      <p className="path">{project.path}</p>

      <section>
        <h2>Índice</h2>
        {'unavailable' in stats ? (
          <p className="warning">{stats.reason}</p>
        ) : (
          <dl className="stat-grid">
            <div><dt>Documentos</dt><dd>{stats.documents}</dd></div>
            <div><dt>Chunks</dt><dd>{stats.chunks}</dd></div>
            <div><dt>Embeddings</dt><dd>{stats.embeddings}</dd></div>
          </dl>
        )}
      </section>

      <section>
        <h2>Chamadas MCP (últimas 24h)</h2>
        {telemetry.totalCalls === 0 ? (
          <p className="empty-hint">Nenhuma chamada registrada ainda.</p>
        ) : (
          <>
            <p>
              <strong>{telemetry.totalCalls}</strong> chamadas · <strong>{telemetry.tokensDelivered}</strong> tokens entregues (real)
            </p>
            <ul className="call-breakdown">
              {telemetry.callsByTool.map((c) => (
                <li key={c.tool}>{c.tool}: {c.count}</li>
              ))}
            </ul>
          </>
        )}
        <p className="estimate-note">
          Economia estimada não é calculada automaticamente — é um proxy (ver <code>ragx trial</code>), não um número ao vivo.
        </p>
      </section>
    </main>
  )
}
```

- [ ] **Step 11: Wire up `App.tsx`**

Replace `src/app/src/App.tsx` entirely (the current content is the default
Vite counter demo — none of it is kept):

```typescript
import { useState } from 'react'
import { useSnapshot } from './hooks/useSnapshot'
import { ProjectList } from './components/ProjectList'
import { ProjectDetail } from './components/ProjectDetail'
import './App.css'

function App() {
  const { snapshot } = useSnapshot()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const projects = snapshot?.projects ?? []
  const selected = projects.find((p) => p.id === selectedId) ?? projects[0] ?? null

  return (
    <div className="app-shell">
      <ProjectList
        projects={projects}
        selectedId={selected?.id ?? null}
        onSelect={setSelectedId}
      />
      <ProjectDetail project={selected} />
    </div>
  )
}

export default App
```

Replace `src/app/src/App.css` with minimal layout styling (no design system
— per spec, "simples e rápido" applies to the implementation effort, not
just runtime behavior):

```css
.app-shell {
  display: flex;
  height: 100vh;
  font-family: system-ui, sans-serif;
}

.project-list {
  width: 240px;
  border-right: 1px solid #ddd;
  overflow-y: auto;
  padding: 8px;
}

.project-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.project-list button {
  width: 100%;
  text-align: left;
  padding: 8px;
  border: none;
  background: none;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
}

.project-list button.selected {
  background: #eef;
}

.status {
  font-size: 0.75em;
  padding: 2px 6px;
  border-radius: 4px;
  background: #eee;
}

.status-ok { background: #dfd; }
.status-degraded { background: #fdd; }

.project-detail {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

.stat-grid {
  display: flex;
  gap: 24px;
}

.stat-grid dt {
  font-size: 0.8em;
  color: #666;
}

.stat-grid dd {
  font-size: 1.5em;
  margin: 0;
}

.warning {
  color: #a00;
}

.empty-hint {
  color: #666;
}

.estimate-note {
  font-size: 0.85em;
  color: #666;
  margin-top: 12px;
}

.call-breakdown {
  list-style: none;
  padding: 0;
  font-size: 0.9em;
  color: #444;
}
```

- [ ] **Step 12: Manual verification**

Run: `cd src/app && npm run dev:electron`
Expected: window opens showing the two-column layout; empty-hub message on
the left if no project is registered yet on this machine, or real project
names if `ragx project register` was already run. Selecting a project
updates the right panel without a full reload.

- [ ] **Step 13: Run the full frontend test suite**

Run: `cd src/app && npm test`
Expected: all passing (hub + telemetry from Task 2, useSnapshot + ProjectList from this task)

- [ ] **Step 14: Commit**

```bash
git add src/app/src/ src/app/package.json src/app/package-lock.json src/app/vite.config.ts
git commit -m "feat(app): UI de lista de projetos + painel de detalhe"
```

---

### Task 5: Ações sob demanda — economia estimada (`ragx trial`) e achados de segurança

**Files:**
- Modify: `src/app/electron/main.ts` (two more `ipcMain.handle` entries, spawning `ragx` as a child process)
- Modify: `src/app/electron/preload.ts` (two more bridge methods)
- Modify: `src/app/src/types/ragx-bridge.d.ts` (add the two new methods + their result types)
- Modify: `src/app/src/components/ProjectDetail.tsx` (add two buttons + result panels)
- Test: `src/app/electron/data/__tests__/run-ragx-command.test.ts`
- Create: `src/app/electron/data/run-ragx-command.ts`

**Interfaces:**
- Consumes: `ProjectSnapshot.path` (Task 4's type) to know which directory to run the command in.
- Produces: `window.ragx.runTrial(projectPath: string): Promise<TrialResult>` and
  `window.ragx.runSecurityScan(projectPath: string): Promise<SecurityScanResult>` — terminal
  IPC methods of this plan, consumed only by `ProjectDetail.tsx` in this same task.

This task implements the spec's "Direita" bullets that Tasks 1-4 deferred:
*"link/botão 'ver economia estimada' que roda `ragx trial --json` sob
demanda"* and *"Achados de segurança do último `ragx security scan`... sob
demanda"*. Both run the already-installed `ragx` CLI as a child process —
no new Python code, no IPC polling (spec: these are explicitly NOT part of
the 5s poll, only Task 3's snapshot is).

- [ ] **Step 1: Write the failing test for the child-process runner**

Create `src/app/electron/data/__tests__/run-ragx-command.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { EventEmitter } from 'node:events'

vi.mock('node:child_process', () => ({
  spawn: vi.fn(),
}))

import { spawn } from 'node:child_process'
import { runRagxCommand } from '../run-ragx-command'

function fakeChildProcess(stdout: string, exitCode: number) {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter
    stderr: EventEmitter
  }
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  queueMicrotask(() => {
    child.stdout.emit('data', Buffer.from(stdout))
    child.emit('close', exitCode)
  })
  return child
}

describe('runRagxCommand', () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset()
  })

  it('resolve com o JSON parseado do stdout quando o comando sai com codigo 0', async () => {
    vi.mocked(spawn).mockReturnValue(fakeChildProcess('{"ok": true, "n": 3}\n', 0) as never)

    const result = await runRagxCommand('C:\\projeto', ['trial', '--json'])

    expect(result).toEqual({ ok: true, n: 3 })
    expect(spawn).toHaveBeenCalledWith('ragx', ['trial', '--json'], { cwd: 'C:\\projeto' })
  })

  it('rejeita quando o comando sai com codigo diferente de zero', async () => {
    vi.mocked(spawn).mockReturnValue(fakeChildProcess('', 1) as never)

    await expect(runRagxCommand('C:\\projeto', ['trial', '--json'])).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && npx vitest run electron/data/__tests__/run-ragx-command.test.ts`
Expected: FAIL — `Cannot find module '../run-ragx-command'`

- [ ] **Step 3: Implement the runner**

Create `src/app/electron/data/run-ragx-command.ts`:

```typescript
import { spawn } from 'node:child_process'

export function runRagxCommand(cwd: string, args: string[]): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = spawn('ragx', args, { cwd })
    let stdout = ''
    let stderr = ''

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8')
    })
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf-8')
    })
    child.on('error', reject)
    child.on('close', (code: number) => {
      if (code !== 0) {
        reject(new Error(`ragx ${args.join(' ')} saiu com código ${code}: ${stderr.slice(0, 500)}`))
        return
      }
      try {
        resolve(JSON.parse(stdout))
      } catch (err) {
        reject(new Error(`saída de "ragx ${args.join(' ')}" não é JSON válido: ${String(err)}`))
      }
    })
  })
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && npx vitest run electron/data/__tests__/run-ragx-command.test.ts`
Expected: 2 passed

- [ ] **Step 5: Add the two IPC handlers**

In `src/app/electron/main.ts`, add to the imports:

```typescript
import { runRagxCommand } from './data/run-ragx-command'
```

Add alongside the existing `ipcMain.handle('ragx:get-snapshot', ...)` line
from Task 3:

```typescript
ipcMain.handle('ragx:run-trial', (_event, projectPath: string) =>
  runRagxCommand(projectPath, ['trial', '--json']),
)
ipcMain.handle('ragx:run-security-scan', (_event, projectPath: string) =>
  runRagxCommand(projectPath, ['security', 'scan', '.', '--json']),
)
```

- [ ] **Step 6: Extend the preload bridge**

In `src/app/electron/preload.ts`, add to the `contextBridge.exposeInMainWorld('ragx', {...})` object (from Task 3 — read the current file first, add alongside `getSnapshot`/`onSnapshot`, don't replace them):

```typescript
runTrial: (projectPath: string): Promise<unknown> =>
  ipcRenderer.invoke('ragx:run-trial', projectPath),
runSecurityScan: (projectPath: string): Promise<unknown> =>
  ipcRenderer.invoke('ragx:run-security-scan', projectPath),
```

- [ ] **Step 7: Extend the bridge type**

In `src/app/src/types/ragx-bridge.d.ts`, add above `declare global`:

```typescript
export interface TrialResult {
  totals: {
    baseline_tokens: number
    ragx_tokens: number
    saved_ratio: number
    source_coverage: number
  }
}

export interface SecurityScanResult {
  blocked: Array<{ path: string; rule_id: string }>
  redacted: Array<{ path: string }>
}
```

Add `runTrial` and `runSecurityScan` to the `RagxBridge` interface:

```typescript
export interface RagxBridge {
  getSnapshot: () => Promise<Snapshot>
  onSnapshot: (cb: (snapshot: Snapshot) => void) => () => void
  runTrial: (projectPath: string) => Promise<TrialResult>
  runSecurityScan: (projectPath: string) => Promise<SecurityScanResult>
}
```

Note: verify `ragx trial --json`'s actual top-level shape (`{"budget":...,
"cases":..., "results": [...], "totals": {...}}` per
`src/ragx/cli/commands/trial_cmd.py`, already built earlier this session)
and `ragx security scan . --json`'s actual shape (check
`src/ragx/cli/commands/security.py`'s `--json` branch) against these types
before wiring the UI in Step 8 — this plan's author read `trial_cmd.py`'s
JSON output structure once, months before this plan might be executed;
re-confirm it hasn't changed.

- [ ] **Step 8: Add the buttons and result panels to `ProjectDetail`**

Modify `src/app/src/components/ProjectDetail.tsx` — add `useState` for the
two on-demand results, and two buttons. Read the current file (from Task 4)
first and extend it; the changes are:

```typescript
import { useState } from 'react'
import type { ProjectSnapshot, TrialResult, SecurityScanResult } from '../types/ragx-bridge'

// ...dentro do componente ProjectDetail, antes do "return":
const [trial, setTrial] = useState<TrialResult | 'loading' | 'error' | null>(null)
const [scan, setScan] = useState<SecurityScanResult | 'loading' | 'error' | null>(null)

async function handleRunTrial() {
  if (!project) return
  setTrial('loading')
  try {
    setTrial(await window.ragx.runTrial(project.path ?? ''))
  } catch {
    setTrial('error')
  }
}

async function handleRunScan() {
  if (!project) return
  setScan('loading')
  try {
    setScan(await window.ragx.runSecurityScan(project.path ?? ''))
  } catch {
    setScan('error')
  }
}
```

Add inside the `<section>` that already shows tokens delivered (right after
the existing `<p className="estimate-note">` paragraph from Task 4):

```jsx
<button type="button" onClick={handleRunTrial} disabled={trial === 'loading'}>
  {trial === 'loading' ? 'Calculando…' : 'Ver economia estimada'}
</button>
{trial && trial !== 'loading' && trial !== 'error' && (
  <p className="estimate-result">
    Estimativa: {(trial.totals.saved_ratio * 100).toFixed(0)}% de economia ·
    cobertura de fonte {(trial.totals.source_coverage * 100).toFixed(0)}%
  </p>
)}
{trial === 'error' && <p className="warning">Não foi possível calcular agora.</p>}
```

Add a new `<section>` after it:

```jsx
<section>
  <h2>Segurança</h2>
  <button type="button" onClick={handleRunScan} disabled={scan === 'loading'}>
    {scan === 'loading' ? 'Escaneando…' : 'Atualizar achados de segurança'}
  </button>
  {scan && scan !== 'loading' && scan !== 'error' && (
    <p>{scan.blocked.length} bloqueados · {scan.redacted.length} redigidos</p>
  )}
  {scan === 'error' && <p className="warning">Não foi possível escanear agora.</p>}
</section>
```

- [ ] **Step 9: Manual verification**

Run: `cd src/app && npm run dev:electron`, select a real registered
project, click "Ver economia estimada" — expected: button shows
"Calculando…", then the estimate line appears, clearly labeled, never
overwriting the real "tokens entregues" number from Task 4. Click "Atualizar
achados de segurança" — expected: blocked/redacted counts appear.

- [ ] **Step 10: Run the full frontend test suite**

Run: `cd src/app && npm test`
Expected: all passing, including the 2 new `run-ragx-command` tests

- [ ] **Step 11: Commit**

```bash
git add src/app/electron/main.ts src/app/electron/preload.ts src/app/electron/data/run-ragx-command.ts src/app/electron/data/__tests__/run-ragx-command.test.ts src/app/src/types/ragx-bridge.d.ts src/app/src/components/ProjectDetail.tsx
git commit -m "feat(app): economia estimada e achados de seguranca sob demanda"
```

---

### Task 6: Empacotar o .exe

**Files:**
- Create: `src/app/electron-builder.yml`
- Modify: `src/app/package.json` (add `build` field pointing to config, or confirm `electron-builder.yml` is picked up automatically — electron-builder reads a top-level config file by convention, no `package.json` field required when the YAML file is present at the project root)
- Modify: `src/app/.gitignore` (add `dist-electron/`, `release/` — read the current `.gitignore` first, Task 1 already may have touched it if `dist/` isn't already listed; don't duplicate entries)

**Interfaces:**
- Consumes: `dist/` (Vite's built renderer, from `npm run build`) and `dist-electron/` (compiled main/preload, from `npm run build:electron:ts`) — both already produced by Task 1/3's scripts.
- Produces: `release/RAGX-Painel-Setup-<version>.exe` — the final deliverable of this plan, nothing downstream depends on it.

- [ ] **Step 1: Write the packaging config**

Create `src/app/electron-builder.yml`:

```yaml
appId: com.ragx.painel
productName: RAGX Painel
directories:
  output: release
files:
  - dist/**/*
  - dist-electron/**/*
  - package.json
win:
  target: nsis
  icon: public/favicon.svg
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
```

Note: `favicon.svg` may not be a valid Windows icon format (NSIS wants
`.ico`) — if `electron-builder` errors on the icon during Step 3, either
drop the `icon:` line (it falls back to Electron's default icon, acceptable
for this version) or convert `public/favicon.svg` to a `.ico` first; don't
block the packaging task on icon artwork.

- [ ] **Step 2: Update `.gitignore`**

Read `src/app/.gitignore`'s current content first (it already has `dist/`,
`node_modules/` from the Vite scaffold). Add, if not already present:

```
dist-electron/
release/
```

- [ ] **Step 3: Build the installer**

Run: `cd src/app && npm run package`
Expected: `src/app/release/RAGX Painel Setup <version>.exe` is produced, no
build error. If `better-sqlite3` fails to load at runtime after packaging
(native module ABI mismatch between the Node version used to `npm install`
and Electron's bundled Node), run `npx electron-builder install-app-deps`
before `npm run package` and retry — this rebuilds native modules against
Electron's ABI, a known requirement for `better-sqlite3` specifically that
`electron-builder` does not always trigger automatically depending on npm
version.

- [ ] **Step 4: Verify the packaged app runs standalone**

Run the produced `.exe` directly (double-click or `& "src/app/release/RAGX Painel Setup <version>.exe"` from PowerShell) — expected: installs and launches without needing `npm run dev` running anywhere, shows the same two-column UI as Task 4's dev-mode verification.

- [ ] **Step 5: Commit**

```bash
git add src/app/electron-builder.yml src/app/.gitignore
git commit -m "build(app): empacota o painel como instalador .exe (electron-builder)"
```

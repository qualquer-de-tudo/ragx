import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

/**
 * O que o instalador mudou na máquina, para o desinstalador desfazer só isso.
 * `pathAdded` é `true` apenas quando ESTE app pôs `binDir` no PATH: se a pasta
 * já estava lá (por causa do `uv` ou do `claude.exe`), remover seria quebrar
 * outro programa.
 */
export interface BootstrapState {
  pathAdded: boolean
  binDir: string | null
}

const EMPTY_STATE: BootstrapState = { pathAdded: false, binDir: null }

const stateFile = (dir: string): string => path.join(dir, 'bootstrap-state.json')

export function readState(dir: string): BootstrapState {
  try {
    const raw = JSON.parse(fs.readFileSync(stateFile(dir), 'utf-8')) as Partial<BootstrapState>
    return {
      pathAdded: raw.pathAdded === true,
      binDir: typeof raw.binDir === 'string' ? raw.binDir : null,
    }
  } catch {
    return { ...EMPTY_STATE }
  }
}

export function writeState(dir: string, state: BootstrapState): void {
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(stateFile(dir), JSON.stringify(state, null, 2) + '\n', 'utf-8')
}

export interface PathDeps {
  getUserPath(): Promise<string>
  setUserPath(value: string): Promise<void>
  readState(): BootstrapState
  writeState(state: BootstrapState): void
}

const sameDir = (a: string, b: string): boolean => a.replace(/[\\/]+$/, '').toLowerCase() === b.replace(/[\\/]+$/, '').toLowerCase()

/** Põe `binDir` no PATH do usuário se ainda não estiver. Idempotente. */
export async function ensureUserPath(binDir: string, deps: PathDeps): Promise<{ added: boolean }> {
  const current = await deps.getUserPath()
  const parts = current.split(';').filter((p) => p.length > 0)
  if (parts.some((p) => sameDir(p, binDir))) return { added: false }
  await deps.setUserPath([...parts, binDir].join(';'))
  deps.writeState({ pathAdded: true, binDir })
  return { added: true }
}

/** Tira do PATH só o que este app pôs (`pathAdded`); caso contrário não mexe. */
export async function removeFromUserPath(deps: PathDeps): Promise<{ removed: boolean }> {
  const state = deps.readState()
  if (!state.pathAdded || state.binDir === null) return { removed: false }
  const binDir = state.binDir
  const parts = (await deps.getUserPath()).split(';').filter((p) => p.length > 0)
  const kept = parts.filter((p) => !sameDir(p, binDir))
  if (kept.length !== parts.length) await deps.setUserPath(kept.join(';'))
  deps.writeState({ ...EMPTY_STATE })
  return { removed: kept.length !== parts.length }
}

// -- implementação real (PowerShell) ---------------------------------------
// `SetEnvironmentVariable(..., 'User')` também avisa o Windows (WM_SETTINGCHANGE),
// que `reg add` não faz. O valor novo viaja por variável de ambiente, nunca
// interpolado no texto do script.

function powershellExe(): string {
  const root = process.env.SystemRoot ?? 'C:\\Windows'
  return path.win32.join(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
}

function runPowerShell(script: string, extraEnv: Record<string, string> = {}): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      powershellExe(),
      ['-NoProfile', '-NonInteractive', '-Command', script],
      { windowsHide: true, encoding: 'utf-8', timeout: 20000, env: { ...process.env, ...extraEnv } },
      (err, stdout, stderr) => (err ? reject(new Error(stderr || err.message)) : resolve(stdout)),
    )
  })
}

export function realPathDeps(stateDir: string): PathDeps {
  return {
    getUserPath: async () => (await runPowerShell("[Environment]::GetEnvironmentVariable('Path','User')")).trim(),
    setUserPath: async (value) => {
      await runPowerShell("[Environment]::SetEnvironmentVariable('Path',$env:RAGX_NEW_PATH,'User')", {
        RAGX_NEW_PATH: value,
      })
    },
    readState: () => readState(stateDir),
    writeState: (s) => writeState(stateDir, s),
  }
}

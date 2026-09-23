import { execFileText } from '../system/exec'
import type { ExecFn } from '../system/exec'
import { httpGetJson } from '../system/http'
import { resolveOllama } from './paths'
import type { GpuVendor, OllamaEnvironment, OllamaMode } from '../../src/types/ragx-bridge'

export interface EnvDeps {
  exec: ExecFn
  httpGetJson: (url: string, timeoutMs: number) => Promise<unknown | null>
  platform: NodeJS.Platform
  arch: string
  /** Executável nativo, mesmo fora do PATH. */
  resolveNativePath: () => string | null
}

const TAGS_URL = 'http://localhost:11434/api/tags'

const VENDOR_PATTERNS: Array<[GpuVendor, RegExp]> = [
  ['nvidia', /geforce|rtx|gtx|quadro|nvidia/i],
  ['amd', /amd|radeon/i],
  ['apple', /apple/i],
  ['intel', /intel/i],
]

export function classifyGpu(
  names: string[],
  platform: NodeJS.Platform,
  arch: string,
): { vendor: GpuVendor; name: string | null } {
  if (platform === 'darwin') {
    return { vendor: arch === 'arm64' ? 'apple' : 'unknown', name: null }
  }
  const clean = names.map((n) => n.trim()).filter((n) => n.length > 0)
  if (clean.length === 0) return { vendor: 'none', name: null }
  for (const [vendor, pattern] of VENDOR_PATTERNS) {
    const hit = clean.find((n) => pattern.test(n))
    if (hit !== undefined) return { vendor, name: hit }
  }
  return { vendor: 'unknown', name: clean[0] }
}

export function recommend(env: Omit<OllamaEnvironment, 'recommendation'>): { mode: 'docker' | 'native'; reason: string } {
  if (env.platform === 'darwin') {
    return { mode: 'native', reason: 'No macOS o Docker não usa a GPU. O Ollama local usa a GPU do Mac.' }
  }
  const dockerInstalled = env.docker.installed
  if (env.gpu.vendor === 'nvidia') {
    return dockerInstalled
      ? { mode: 'docker', reason: 'O container consegue usar sua GPU NVIDIA.' }
      : { mode: 'native', reason: 'Sem Docker instalado, o Ollama local usa sua GPU NVIDIA.' }
  }
  if (env.gpu.vendor === 'amd') {
    return { mode: 'native', reason: 'O Docker não repassa GPU AMD. O Ollama local usa a sua placa.' }
  }
  return dockerInstalled
    ? { mode: 'docker', reason: 'Sem GPU compatível com o Docker, o container resolve e isola o Ollama.' }
    : { mode: 'native', reason: 'Sem Docker instalado, use o Ollama local.' }
}

/** Nunca lança: qualquer falha vira `fallback`. */
async function safe<T>(run: () => Promise<T> | T, fallback: T): Promise<T> {
  try {
    return await run()
  } catch {
    return fallback
  }
}

function lines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
}

async function listGpuNames(d: EnvDeps): Promise<string[]> {
  if (d.platform === 'win32') {
    const r = await d.exec('powershell', [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      '(Get-CimInstance Win32_VideoController).Name',
    ])
    return r.code === 0 ? lines(r.stdout) : []
  }
  if (d.platform === 'linux') {
    const r = await d.exec('lspci', [])
    return r.code === 0 ? lines(r.stdout).filter((l) => /VGA|3D|Display/.test(l)) : []
  }
  return []
}

async function detectDocker(d: EnvDeps): Promise<{
  docker: OllamaEnvironment['docker']
  container: OllamaEnvironment['container']
}> {
  const version = await d.exec('docker', ['--version'])
  if (version.code !== 0) {
    return { docker: { installed: false, running: false }, container: { exists: false, running: false } }
  }
  const info = await d.exec('docker', ['info', '--format', '{{.ServerVersion}}'])
  if (info.code !== 0) {
    return { docker: { installed: true, running: false }, container: { exists: false, running: false } }
  }
  const ps = await d.exec('docker', ['ps', '-a', '--filter', 'name=^ollama$', '--format', '{{.State}}'])
  const state = ps.code === 0 ? (lines(ps.stdout)[0] ?? '') : ''
  return {
    docker: { installed: true, running: true },
    container: { exists: state !== '', running: state === 'running' },
  }
}

async function nativeRunning(d: EnvDeps): Promise<boolean> {
  if (d.platform === 'win32') {
    const r = await d.exec('tasklist', ['/FI', 'IMAGENAME eq ollama.exe', '/FO', 'CSV', '/NH'])
    return r.code === 0 && r.stdout.toLowerCase().includes('ollama.exe')
  }
  const r = await d.exec('pgrep', ['-x', 'ollama'])
  return r.code === 0
}

function extractModels(json: unknown): string[] {
  if (typeof json !== 'object' || json === null) return []
  const models = (json as { models?: unknown }).models
  if (!Array.isArray(models)) return []
  const names: string[] = []
  for (const m of models) {
    const name = (m as { name?: unknown } | null)?.name
    if (typeof name === 'string') names.push(name)
  }
  return names
}

function toSupportedPlatform(p: NodeJS.Platform): OllamaEnvironment['platform'] {
  return p === 'win32' || p === 'darwin' ? p : 'linux'
}

/** Nunca lança: qualquer falha vira o campo "ausente". */
export async function detectOllama(d: EnvDeps): Promise<OllamaEnvironment> {
  const platform = toSupportedPlatform(d.platform)
  const [gpuNames, dockerInfo, nativePath, isNativeRunning, json] = await Promise.all([
    safe(() => listGpuNames(d), [] as string[]),
    safe(() => detectDocker(d), {
      docker: { installed: false, running: false },
      container: { exists: false, running: false },
    }),
    safe(() => d.resolveNativePath(), null),
    safe(() => nativeRunning(d), false),
    safe(() => d.httpGetJson(TAGS_URL, 3000), null),
  ])

  const gpu = classifyGpu(gpuNames, d.platform, d.arch)
  const { docker, container } = dockerInfo
  const native = { installed: nativePath !== null, path: nativePath, running: isNativeRunning }
  const apiUp = json !== null

  let mode: OllamaMode
  if (container.running && native.running) mode = 'conflict'
  else if (container.running) mode = 'docker'
  else if (native.running) mode = 'native'
  else if (apiUp) mode = 'native'
  else mode = 'none'

  const partial: Omit<OllamaEnvironment, 'recommendation'> = {
    platform,
    gpu,
    docker,
    container,
    native,
    canInstallNative: platform === 'win32',
    apiUp,
    models: extractModels(json),
    mode,
  }
  return { ...partial, recommendation: recommend(partial) }
}

export function defaultEnvDeps(): EnvDeps {
  return {
    exec: execFileText,
    httpGetJson,
    platform: process.platform,
    arch: process.arch,
    resolveNativePath: () => resolveOllama(),
  }
}

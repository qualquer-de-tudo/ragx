import fs from 'node:fs'
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
  /**
   * Lê um arquivo de texto (`/proc/<pid>/cgroup`); `null` se não der. Sem
   * ela, todo pid do `pgrep` conta como Ollama local.
   */
  readFile?: (p: string) => string | null
  /**
   * Nomes das placas de vídeo. O `defaultEnvDeps` passa um cache de processo
   * (a placa não muda com o painel aberto, e a consulta do Windows abre um
   * PowerShell); sem ela, `detectOllama` consulta pelo `exec` a cada vez.
   */
  gpuNames?: () => Promise<string[]>
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

/** Nomes das placas de vídeo; `null` quando a consulta falhou (e vale tentar de novo). */
export async function queryGpuNames(exec: ExecFn, platform: NodeJS.Platform): Promise<string[] | null> {
  if (platform === 'win32') {
    const r = await exec('powershell', [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      '(Get-CimInstance Win32_VideoController).Name',
    ])
    return r.code === 0 ? lines(r.stdout) : null
  }
  if (platform === 'linux') {
    const r = await exec('lspci', [])
    return r.code === 0 ? lines(r.stdout).filter((l) => /VGA|3D|Display/.test(l)) : null
  }
  return []
}

/**
 * Guarda os nomes das placas depois da primeira consulta que deu certo.
 * Consulta que falhou (ou lançou) devolve `[]` e não fica guardada; pedidos
 * simultâneos dividem a mesma consulta. Nunca rejeita.
 */
export function onceGpuNames(query: () => Promise<string[] | null>): () => Promise<string[]> {
  let cached: string[] | null = null
  let inFlight: Promise<string[]> | null = null
  return () => {
    if (cached !== null) return Promise.resolve(cached)
    if (inFlight !== null) return inFlight
    const run = Promise.resolve()
      .then(query)
      .then(
        (names) => {
          if (names !== null) cached = names
          return names ?? []
        },
        () => [] as string[],
      )
      .finally(() => {
        if (inFlight === run) inFlight = null
      })
    inFlight = run
    return run
  }
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

/** cgroup de processo de container (Docker, containerd, Kubernetes). */
const CONTAINER_CGROUP = /docker|containerd|kubepods/i

/**
 * Fora do Windows, `pgrep -x ollama` também acha o `ollama` que roda DENTRO
 * do container (no Linux ele é um processo do host). Um pid cujo
 * `/proc/<pid>/cgroup` cita docker, containerd ou kubepods é do container e
 * não conta; cgroup ilegível (processo sumiu, macOS sem `/proc`) conta.
 */
async function nativeRunning(d: EnvDeps): Promise<boolean> {
  if (d.platform === 'win32') {
    const r = await d.exec('tasklist', ['/FI', 'IMAGENAME eq ollama.exe', '/FO', 'CSV', '/NH'])
    return r.code === 0 && r.stdout.toLowerCase().includes('ollama.exe')
  }
  const r = await d.exec('pgrep', ['-x', 'ollama'])
  if (r.code !== 0) return false
  const pids = lines(r.stdout).filter((l) => /^\d+$/.test(l))
  if (pids.length === 0) return true
  return pids.some((pid) => {
    const cgroup = readCgroup(d, pid)
    return cgroup === null || !CONTAINER_CGROUP.test(cgroup)
  })
}

function readCgroup(d: EnvDeps, pid: string): string | null {
  try {
    return d.readFile?.(`/proc/${pid}/cgroup`) ?? null
  } catch {
    return null
  }
}

async function gpuNamesOf(d: EnvDeps): Promise<string[]> {
  if (d.gpuNames) return d.gpuNames()
  return (await queryGpuNames(d.exec, d.platform)) ?? []
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
    safe(() => gpuNamesOf(d), [] as string[]),
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

/** Uma consulta de placas de vídeo por processo (e não um PowerShell a cada 30 s). */
const processGpuNames = onceGpuNames(() => queryGpuNames(execFileText, process.platform))

function readTextFile(p: string): string | null {
  try {
    return fs.readFileSync(p, 'utf-8')
  } catch {
    return null
  }
}

export function defaultEnvDeps(): EnvDeps {
  return {
    exec: execFileText,
    httpGetJson,
    platform: process.platform,
    arch: process.arch,
    resolveNativePath: () => resolveOllama(),
    readFile: readTextFile,
    gpuNames: processGpuNames,
  }
}

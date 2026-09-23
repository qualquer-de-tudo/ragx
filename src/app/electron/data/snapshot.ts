import fs from 'node:fs'
import { readHubRegistry } from './hub'
import { readProjectStats } from './project-stats'
import { readTelemetry } from './telemetry'
import { readStatusFile } from './status-file'
import type { StatusFile } from './status-file'
import { readGitHead } from './git'
import type { GitHead } from './git'
import type { HubProject, ProjectStats, ProjectStatsUnavailable, TelemetrySummary } from './types'
import type { IndexInfo, ProjectSnapshot, Snapshot } from '../../src/types/ragx-bridge'

const TELEMETRY_WINDOW_HOURS = 24

export interface SnapshotDeps {
  readRegistry: () => HubProject[]
  readStatus: (projectPath: string) => StatusFile | null
  readStats: (projectPath: string) => ProjectStats | ProjectStatsUnavailable
  readTelemetry: (projectPath: string, sinceHours: number) => TelemetrySummary
  readGit: (projectPath: string) => Promise<GitHead | null>
  exists: (projectPath: string) => boolean
  /** O processo que segura a indexação (`status.json` `running.pid`) ainda existe? */
  isPidAlive: (pid: number) => boolean
}

type KillFn = (pid: number, signal: 0) => unknown

/**
 * Sinal 0 não mata nada: só pergunta ao SO se o processo existe (funciona
 * também no Windows). ESRCH é "não existe"; EPERM é "existe, mas é de outro
 * usuário", então conta como vivo. Um pid inválido (não inteiro positivo)
 * não dá para checar e fica como vivo: melhor mostrar "Indexando…" a mais do
 * que esconder uma indexação de verdade.
 */
export function isPidAlive(pid: number, kill: KillFn = (p, sig) => process.kill(p, sig)): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return true
  try {
    kill(pid, 0)
    return true
  } catch (err) {
    return (err as NodeJS.ErrnoException).code !== 'ESRCH'
  }
}

const REAL_DEPS: SnapshotDeps = {
  readRegistry: readHubRegistry,
  readStatus: readStatusFile,
  readStats: readProjectStats,
  readTelemetry,
  readGit: readGitHead,
  exists: (p) => fs.existsSync(p),
  isPidAlive: (pid) => isPidAlive(pid),
}

const EMPTY_TELEMETRY: TelemetrySummary = { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null }

// Cache do ultimo snapshot valido - usado como fallback se readRegistry() em
// si falhar (ex.: registry.json corrompido/truncado por escrita
// concorrente), para nao propagar um erro nao tratado ate o poll timer ou o
// handler IPC (comportamento migrado do main.ts original, ver Finding 2 da
// revisao final da Task 1).
let lastGoodSnapshot: Snapshot | null = null

export async function buildSnapshot(deps: Partial<SnapshotDeps> = {}): Promise<Snapshot> {
  const d: SnapshotDeps = { ...REAL_DEPS, ...deps }

  let registry: HubProject[]
  try {
    registry = d.readRegistry()
  } catch (err) {
    console.error('readHubRegistry() falhou - registry.json pode estar corrompido/em escrita:', err)
    return lastGoodSnapshot ?? { projects: [], generatedAt: new Date().toISOString() }
  }

  const projects = await Promise.all(registry.map((proj) => buildProjectSnapshot(proj, d)))

  const snapshot: Snapshot = { projects, generatedAt: new Date().toISOString() }
  lastGoodSnapshot = snapshot
  return snapshot
}

async function buildProjectSnapshot(proj: HubProject, d: SnapshotDeps): Promise<ProjectSnapshot> {
  const exists = proj.path !== null && d.exists(proj.path)

  // Pasta ausente (ou projeto só de federação, sem path local): não chama
  // git nem status - não há nada de útil pra ler no disco.
  if (!exists || proj.path === null) {
    return {
      id: proj.id,
      name: proj.name,
      path: proj.path,
      exists,
      embeddingModel: proj.embeddingModel,
      embeddingProvider: null,
      visibility: proj.visibility,
      counts: null,
      countsUnavailableReason: proj.path
        ? 'pasta do projeto não existe mais'
        : 'projeto sem caminho local (só federação)',
      index: null,
      git: null,
      hooksInstalled: null,
      running: null,
      pending: false,
      lastError: null,
      hasStatusFile: false,
      telemetry: EMPTY_TELEMETRY,
    }
  }

  const projectPath = proj.path

  // Falha em qualquer leitura isola aquele projeto (o campo correspondente
  // vira null/vazio), nunca derruba o snapshot inteiro.
  let status: StatusFile | null = null
  try {
    status = d.readStatus(projectPath)
  } catch (err) {
    console.error(`readStatusFile falhou para o projeto "${proj.name}":`, err)
  }

  let git: GitHead | null = null
  try {
    git = await d.readGit(projectPath)
  } catch (err) {
    console.error(`readGitHead falhou para o projeto "${proj.name}":`, err)
  }

  let counts: ProjectSnapshot['counts'] = null
  let countsUnavailableReason: string | null = null
  if (status) {
    counts = {
      documents: status.counts.documents,
      chunks: status.counts.chunks,
      embeddings: status.counts.embeddings,
      pendingEmbeddings: status.counts.pending_embeddings,
    }
  } else {
    try {
      const stats = d.readStats(projectPath)
      if ('unavailable' in stats) {
        countsUnavailableReason = stats.reason
      } else {
        counts = {
          documents: stats.documents,
          chunks: stats.chunks,
          embeddings: stats.embeddings,
          pendingEmbeddings: Math.max(stats.chunks - stats.embeddings, 0),
        }
      }
    } catch (err) {
      console.error(`readProjectStats falhou para o projeto "${proj.name}":`, err)
      countsUnavailableReason = 'falha ao ler estatísticas do projeto'
    }
  }

  let telemetry: TelemetrySummary = EMPTY_TELEMETRY
  try {
    telemetry = d.readTelemetry(projectPath, TELEMETRY_WINDOW_HOURS)
  } catch (err) {
    console.error(`readTelemetry falhou para o projeto "${proj.name}":`, err)
  }

  const index: IndexInfo | null = status?.index
    ? {
        finishedAt: status.index.finished_at,
        mode: status.index.mode,
        source: status.index.source,
        branch: status.index.branch,
        commit: status.index.commit,
      }
    : null

  return {
    id: proj.id,
    name: proj.name,
    path: proj.path,
    exists,
    embeddingModel: proj.embeddingModel,
    embeddingProvider: status?.embedding.provider ?? null,
    visibility: proj.visibility,
    counts,
    countsUnavailableReason,
    index,
    git,
    hooksInstalled: status?.hooks.installed ?? null,
    running: runningFrom(status, d, proj.name),
    pending: status?.pending ?? false,
    lastError: status?.last_error ?? null,
    hasStatusFile: status !== null,
    telemetry,
  }
}

/**
 * `running` do `status.json` só vale enquanto o processo dono existe (spec
 * A2): um índice cancelado pela fila (`kill`) ou um hook em segundo plano
 * que morreu não chegam a limpar o campo, e o card ficaria "Indexando…"
 * para sempre.
 */
function runningFrom(status: StatusFile | null, d: SnapshotDeps, projectName: string): ProjectSnapshot['running'] {
  if (!status?.running) return null
  let alive = true
  try {
    alive = d.isPidAlive(status.running.pid)
  } catch (err) {
    console.error(`isPidAlive falhou para o projeto "${projectName}":`, err)
  }
  return alive ? { source: status.running.source, startedAt: status.running.started_at } : null
}

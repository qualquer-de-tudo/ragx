/*
 * Leitura defensiva do JSON de `ragx status --json` (Task 9). A resposta vem
 * de um processo externo: nada aqui confia no formato. Campo com tipo errado
 * vira "sem dado", motivo de tipo desconhecido é ignorado, e só o que passou
 * pela validação chega à tela.
 */
import { formatNumber } from './format'

export type StaleReason =
  | { kind: 'branch_changed'; indexed: string; current: string }
  | { kind: 'commits_since_index'; count: number | null }
  | { kind: 'uncommitted_changes'; count: number }
  | { kind: 'pending_embeddings'; count: number }

export type FreshnessState = 'fresh' | 'stale' | 'unknown'

export interface Freshness {
  state: FreshnessState
  reasons: StaleReason[]
}

export interface IndexRun {
  /** Chave estável para a lista. */
  key: string
  startedAt: string | null
  finishedAt: string | null
  mode: string | null
  source: string | null
  branch: string | null
  commit: string | null
  /** Arquivos reindexados; `null` quando o run não registrou. */
  indexed: number | null
  error: string | null
}

export interface ProjectStatus {
  freshness: Freshness
  runs: IndexRun[]
}

type Obj = Record<string, unknown>

function isObj(v: unknown): v is Obj {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null
}

function count(v: unknown): number | null {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0 ? v : null
}

function date(v: unknown): string | null {
  const s = str(v)
  return s !== null && !Number.isNaN(Date.parse(s)) ? s : null
}

function parseReason(v: unknown): StaleReason | null {
  if (!isObj(v)) return null
  switch (v.kind) {
    case 'branch_changed': {
      const indexed = str(v.indexed)
      const current = str(v.current)
      return indexed && current ? { kind: 'branch_changed', indexed, current } : null
    }
    case 'commits_since_index':
      // `count` nulo é válido: o git não soube contar (histórico reescrito).
      if (v.count !== null && count(v.count) === null) return null
      return { kind: 'commits_since_index', count: count(v.count) }
    case 'uncommitted_changes':
    case 'pending_embeddings': {
      const n = count(v.count)
      return n === null ? null : { kind: v.kind, count: n }
    }
    default:
      return null
  }
}

function parseFreshness(v: unknown): Freshness {
  if (!isObj(v)) return { state: 'unknown', reasons: [] }
  const state: FreshnessState = v.state === 'fresh' || v.state === 'stale' ? v.state : 'unknown'
  const reasons = Array.isArray(v.reasons)
    ? v.reasons.map(parseReason).filter((r): r is StaleReason => r !== null)
    : []
  return { state, reasons: state === 'unknown' ? [] : reasons }
}

function parseRun(v: unknown, i: number): IndexRun | null {
  if (!isObj(v)) return null
  const id = typeof v.id === 'number' || typeof v.id === 'string' ? String(v.id) : null
  return {
    key: id !== null ? `run-${id}` : `pos-${i}`,
    startedAt: date(v.started_at),
    finishedAt: date(v.finished_at),
    mode: str(v.mode),
    source: str(v.source),
    branch: str(v.git_branch),
    commit: str(v.git_commit),
    indexed: count(v.indexed),
    error: str(v.error),
  }
}

/** `null` quando a resposta nem é um objeto: quem chama mostra erro. */
export function parseProjectStatus(raw: unknown): ProjectStatus | null {
  if (!isObj(raw)) return null
  if (raw.initialized === false) return { freshness: { state: 'unknown', reasons: [] }, runs: [] }
  const runs = Array.isArray(raw.recent_runs)
    ? raw.recent_runs.map(parseRun).filter((r): r is IndexRun => r !== null)
    : []
  return { freshness: parseFreshness(raw.freshness), runs }
}

export function reasonText(r: StaleReason): string {
  switch (r.kind) {
    case 'branch_changed':
      return `O índice é da branch ${r.indexed}; você está em ${r.current}.`
    case 'commits_since_index':
      return r.count === null
        ? 'Há commits depois da última indexação.'
        : `${formatNumber(r.count)} commit(s) depois da última indexação.`
    case 'uncommitted_changes':
      return `${formatNumber(r.count)} arquivo(s) alterado(s) depois da última indexação.`
    case 'pending_embeddings':
      return `${formatNumber(r.count)} chunk(s) sem embedding.`
  }
}

export const UNKNOWN_FRESHNESS_TEXT =
  'Não dá para saber: o projeto não está num repositório git ou ainda não foi indexado com esta versão.'

import type { ProjectSnapshot } from './types/ragx-bridge'
import { hasProblem, isOutdated, type ProjectState } from './state'
import { formatNumber } from './format'

/**
 * Economia dos últimos 14 dias: quanto menos que ler os arquivos inteiros.
 * `null` sem medição (nenhum `build_context` com as duas medidas), para o card
 * não mostrar "0%" como se fosse um resultado.
 */
export function savingsRatio(p: ProjectSnapshot): number | null {
  const s = p.telemetry.savings
  if (!s || s.baseline <= 0) return null
  return 1 - s.delivered / s.baseline
}

export function tokensSaved(p: ProjectSnapshot): number {
  const s = p.telemetry.savings
  return s ? Math.max(0, s.baseline - s.delivered) : 0
}

export function needsAttention(state: ProjectState, attention: string | null = null): boolean {
  return isOutdated(state) || hasProblem(state) || attention !== null
}

/**
 * Problema de embedding que o selo não mostra (RAGX-0199), em texto: buscas das últimas 24 h que caíram para
 * palavra-chave (`degraded` no `mcp.jsonl`), ou embeddings pendentes num projeto do Ollama com o Ollama fora do ar
 * (gerar embeddings não vai andar). `null` quando não há nada a dizer.
 */
export function embeddingAttention(p: ProjectSnapshot, ollamaDown: boolean): string | null {
  const degraded = p.telemetry.degradedCalls ?? 0
  if (degraded > 0) {
    return `${formatNumber(degraded)} busca(s) nas últimas 24 h caíram para palavra-chave: o modelo de embedding não respondeu.`
  }
  if (ollamaDown && p.embeddingProvider === 'ollama' && (p.counts?.pendingEmbeddings ?? 0) > 0) {
    return 'Embeddings pendentes e o Ollama não está respondendo: inicie-o em Conexões.'
  }
  return null
}

export type SortKey = 'nome' | 'uso' | 'estado'

export const SORT_LABEL: Record<SortKey, string> = {
  nome: 'Nome',
  uso: 'Uso recente',
  estado: 'Estado (o que pede atenção primeiro)',
}

/** Do que mais pede atenção ao que está em dia. */
const STATE_RANK: Record<ProjectState, number> = {
  error: 0,
  missing: 1,
  stale: 2,
  embeddings: 3,
  'no-hooks': 4,
  indexing: 5,
  ok: 6,
}

const byName = (a: ProjectSnapshot, b: ProjectSnapshot) => a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' })

/** Ordena sem perder a ordem por nome como desempate. */
export function sortRows<T extends { project: ProjectSnapshot; state: ProjectState }>(rows: readonly T[], key: SortKey): T[] {
  const out = [...rows]
  if (key === 'nome') return out.sort((a, b) => byName(a.project, b.project))
  if (key === 'estado') return out.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state] || byName(a.project, b.project))
  const uso = (p: ProjectSnapshot) => (p.telemetry.lastCallAt ? Date.parse(p.telemetry.lastCallAt) : -Infinity)
  return out.sort((a, b) => uso(b.project) - uso(a.project) || byName(a.project, b.project))
}

export type ListView = 'grade' | 'lista'

// Como a aba do detalhe: vale enquanto o painel estiver aberto.
let lastView: ListView = 'grade'
let lastSort: SortKey = 'nome'

export const listPrefs = {
  view: () => lastView,
  sort: () => lastSort,
  setView: (v: ListView) => {
    lastView = v
  },
  setSort: (s: SortKey) => {
    lastSort = s
  },
}

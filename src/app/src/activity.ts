import type { ActivityEvent } from './types/ragx-bridge'

/** "Em uso agora": houve evento no último minuto. */
export const LIVE_MS = 60_000
const WINDOW_MS = 24 * 60 * 60 * 1000
const MAX = 500

const ms = (ts: string) => Date.parse(ts)

/** Junta os eventos novos aos que já estavam: sem repetir, o mais novo primeiro, só as últimas 24 h. */
export function mergeEvents(prev: readonly ActivityEvent[], incoming: readonly ActivityEvent[], now: number): ActivityEvent[] {
  const byId = new Map<string, ActivityEvent>()
  for (const e of prev) byId.set(e.id, e)
  for (const e of incoming) byId.set(e.id, e)
  const corte = now - WINDOW_MS
  return [...byId.values()]
    .filter((e) => ms(e.ts) >= corte)
    .sort((a, b) => ms(b.ts) - ms(a.ts) || b.id.localeCompare(a.id))
    .slice(0, MAX)
}

/** Projetos com evento no último minuto. `events` vem do mais novo para o mais antigo. */
export function liveProjectIds(events: readonly ActivityEvent[], now: number): Set<string> {
  const out = new Set<string>()
  for (const e of events) {
    if (now - ms(e.ts) > LIVE_MS) break
    out.add(e.projectId)
  }
  return out
}

/** Quem fez: o perfil do Claude quando se sabe, o terminal, ou um agente MCP sem nome. */
export function whoLabel(e: ActivityEvent): string {
  const perfil = e.profile ? ` · ${e.profile}` : ''
  if (e.client === 'claude-code') {
    return e.kind === 'cli' ? `Terminal do Claude${perfil}` : `Claude Code${perfil}`
  }
  if (e.kind === 'cli') return 'Terminal'
  if (e.kind === 'session') return `Claude Code${perfil}`
  return 'Agente MCP'
}

/** O que foi: a ferramenta MCP, o comando da CLI ou a sessão aberta. */
export function whatLabel(e: ActivityEvent): string {
  if (e.kind === 'session') return 'Sessão iniciada'
  if (e.kind === 'cli') return `ragx ${e.name}`
  return e.name
}

export type ActivityFilter = 'all' | 'mcp' | 'cli' | 'session'

export const FILTER_LABEL: Record<ActivityFilter, string> = {
  all: 'Tudo',
  mcp: 'Agentes (MCP)',
  cli: 'Terminal',
  session: 'Sessões',
}

export function filterEvents(events: readonly ActivityEvent[], kind: ActivityFilter, projectId: string | null): ActivityEvent[] {
  return events.filter((e) => (kind === 'all' || e.kind === kind) && (projectId === null || e.projectId === projectId))
}

export interface ActivityTotals {
  calls: number
  sessions: number
  cliCommands: number
  delivered: number
  baseline: number
  projects: number
}

export function totals(events: readonly ActivityEvent[]): ActivityTotals {
  const projetos = new Set<string>()
  const t: ActivityTotals = { calls: 0, sessions: 0, cliCommands: 0, delivered: 0, baseline: 0, projects: 0 }
  for (const e of events) {
    projetos.add(e.projectId)
    if (e.kind === 'mcp') t.calls += 1
    else if (e.kind === 'session') t.sessions += 1
    else t.cliCommands += 1
    // Só a chamada com as duas medidas entra na economia (como no detalhe do projeto).
    if (e.tokensDelivered !== null && e.baselineTokens !== null) {
      t.delivered += e.tokensDelivered
      t.baseline += e.baselineTokens
    }
  }
  t.projects = projetos.size
  return t
}

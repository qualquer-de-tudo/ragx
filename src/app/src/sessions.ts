import type { ActivityEvent } from './types/ragx-bridge'

/** Uma sessão (ou o grupo "sem sessão identificada" de um projeto) vista pelos eventos de 24 h (RAGX-0188). */
export interface SessionGroup {
  /** `projectId` + `session`: o mesmo id em dois projetos NUNCA funde. */
  key: string
  projectId: string
  projectName: string
  /** `null`: eventos sem `session` (log antigo, testes, fora do Claude Code). */
  session: string | null
  client: string | null
  profile: string | null
  startedAt: string
  lastAt: string
  /** Quantos `session_start` houve: inícios repetidos são subagentes, não várias sessões. */
  starts: number
  mcpCalls: number
  /** Comandos `ragx` (CLI) que não são `session_start`. */
  cliCalls: number
  byTool: Array<{ name: string; count: number }>
  delivered: number
  baseline: number
  /** `null` quando nenhum evento do grupo diz se deu certo (log sem `ok`): "sem dado", nunca "0 falhas". */
  failures: number | null
  /** Houve chamada MCP ou comando `ragx` (fora `session_start`) na sessão. */
  usedRagx: boolean
  /** Em ordem cronológica. */
  events: ActivityEvent[]
}

const ms = (ts: string) => Date.parse(ts)

/**
 * Agrupa os eventos por projeto e sessão, do grupo mais recente ao mais antigo (`lastAt`). `events` pode vir em
 * qualquer ordem. O segundo parâmetro existe para a assinatura combinada com a RAGX-0190 (mesma definição de `usedRagx`
 * e `starts`); a contagem não depende do relógio.
 */
export function groupSessions(events: readonly ActivityEvent[], _now?: number): SessionGroup[] {
  void _now
  const groups = new Map<string, SessionGroup>()
  const tools = new Map<string, Map<string, number>>()
  for (const e of events) {
    const session = e.session && e.session !== '' ? e.session : null
    const key = `${e.projectId}\u0000${session ?? ''}`
    let g = groups.get(key)
    if (!g) {
      g = {
        key, projectId: e.projectId, projectName: e.projectName, session, client: e.client, profile: e.profile,
        startedAt: e.ts, lastAt: e.ts, starts: 0, mcpCalls: 0, cliCalls: 0, byTool: [], delivered: 0, baseline: 0,
        failures: null, usedRagx: false, events: [],
      }
      groups.set(key, g)
      tools.set(key, new Map())
    }
    g.events.push(e)
    if (ms(e.ts) < ms(g.startedAt)) g.startedAt = e.ts
    if (ms(e.ts) > ms(g.lastAt)) g.lastAt = e.ts
    g.client ??= e.client
    g.profile ??= e.profile
    if (e.kind === 'session') {
      g.starts += 1
    } else {
      if (e.kind === 'mcp') g.mcpCalls += 1
      else g.cliCalls += 1
      g.usedRagx = true
      const t = tools.get(key)!
      t.set(e.name, (t.get(e.name) ?? 0) + 1)
    }
    if (e.tokensDelivered !== null && e.baselineTokens !== null) {
      g.delivered += e.tokensDelivered
      g.baseline += e.baselineTokens
    }
    if (e.ok !== null) g.failures = (g.failures ?? 0) + (e.ok === false ? 1 : 0)
  }
  const out = [...groups.values()]
  for (const g of out) {
    g.events.sort((a, b) => ms(a.ts) - ms(b.ts) || a.id.localeCompare(b.id))
    g.byTool = [...tools.get(g.key)!].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
  }
  return out.sort((a, b) => ms(b.lastAt) - ms(a.lastAt) || a.key.localeCompare(b.key))
}

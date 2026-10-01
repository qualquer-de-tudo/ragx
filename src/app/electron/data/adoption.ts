import type { AdoptionSummary } from './types'

/**
 * Adoção pelos agentes (RAGX-0190, S13 da spec): das sessões abertas em projeto indexado, quantas chamaram o RAGX.
 *
 * - **Universo** = sessões com um `session_start` em `cli.jsonl` (o hint só o grava com o banco do projeto presente, ou
 *   seja, "sessão em projeto indexado").
 * - **Usou** = existe chamada em `mcp.jsonl` com o MESMO `session` e o mesmo projeto.
 * - Linha sem `session` conta em `unidentified` e fica FORA da razão. Chamada de sessão sem `session_start` conta em
 *   `callsWithoutStart` (hint desligado, ou sessão aberta antes da janela) e também fica fora.
 *
 * Só contagens, datas e ids de projeto: nada de consulta nem de argumento. S13 é de MEDIÇÃO: a spec não fixa meta.
 */
export interface AdoptionSession {
  projectId: string
  projectName: string
  /** `null`: eventos sem `session` (um item por projeto). */
  session: string | null
  /** `ts` do primeiro `session_start`; `null` quando só houve chamadas. */
  startedAt: string | null
  firstAt: string
  lastAt: string
  /** Chamadas MCP e comandos `ragx` (não `session_start`) com esse `session`. */
  calls: number
  /** Todos os eventos do item (para `unidentified`). */
  events: number
}

export const ADOPTION_DAYS = 14

export function computeAdoption(sessions: readonly AdoptionSession[], now: number, days: number = ADOPTION_DAYS): AdoptionSummary {
  const cutoff = now - days * 86_400_000
  let since: string | null = null
  let withCalls = 0
  let total = 0
  let unidentified = 0
  let callsWithoutStart = 0
  const byProject = new Map<string, { projectId: string; projectName: string; sessions: number; withCalls: number }>()

  for (const s of sessions) {
    if (Date.parse(s.lastAt) < cutoff) continue
    if (since === null || Date.parse(s.firstAt) < Date.parse(since)) since = s.firstAt
    if (s.session === null) {
      unidentified += s.events
      continue
    }
    if (s.startedAt === null) {
      if (s.calls > 0) callsWithoutStart += 1
      continue
    }
    total += 1
    const used = s.calls > 0
    if (used) withCalls += 1
    const p = byProject.get(s.projectId) ?? { projectId: s.projectId, projectName: s.projectName, sessions: 0, withCalls: 0 }
    p.sessions += 1
    if (used) p.withCalls += 1
    byProject.set(s.projectId, p)
  }
  return {
    since,
    sessions: total,
    withCalls,
    withoutCalls: total - withCalls,
    unidentified,
    callsWithoutStart,
    byProject: [...byProject.values()].sort((a, b) => b.sessions - a.sessions || a.projectName.localeCompare(b.projectName, 'pt-BR')),
  }
}

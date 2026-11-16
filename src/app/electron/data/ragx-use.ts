import type { ActivityKind } from './types'

/**
 * O que conta como USO do RAGX numa linha de atividade. Um lugar só para a regra: o feed, as sessões, o "Em uso agora"
 * e a adoção (RAGX-0190) liam cada um a sua, e o `nudge` (o lembrete do hook PreToolUse Grep|Glob) virou "comando no
 * terminal" em uns e não em outros. Puro e sem `node:`: o processo principal e o renderer importam o mesmo arquivo.
 */

/** Comando de `cli.jsonl` que só registra que o lembrete de busca foi mostrado: não é uso do RAGX. */
export const NUDGE_COMMAND = 'nudge'
/** Comando de `cli.jsonl` gravado pelo hint do SessionStart: uma sessão (ou retomada) aberta, não uso. */
export const SESSION_START_COMMAND = 'session_start'

/** Tipo do evento de uma linha de `cli.jsonl` pelo `command`. */
export function cliKindFor(command: string): ActivityKind {
  if (command === SESSION_START_COMMAND) return 'session'
  if (command === NUDGE_COMMAND) return 'nudge'
  return 'cli'
}

/** Chamada MCP ou comando de consulta `ragx` (search, context, chunk...): sessão aberta e lembrete não contam. */
export function isRagxUse(e: { kind: ActivityKind }): boolean {
  return e.kind === 'mcp' || e.kind === 'cli'
}

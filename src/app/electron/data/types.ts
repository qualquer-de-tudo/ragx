export interface HubProject {
  id: string
  name: string
  path: string | null
  cloned: boolean
  embeddingModel: string | null
  visibility: string
  status: string
  chunks: number
  lastSync: string | null
}

export interface ProjectStats {
  documents: number
  chunks: number
  embeddings: number
}

export interface ProjectStatsUnavailable {
  unavailable: true
  reason: string
}

export interface TelemetryCallCount {
  tool: string
  count: number
}

/** Um dia do gráfico de economia: só chamadas `build_context` que gravaram as duas medidas. */
export interface SavingsDay {
  /** Data local, `AAAA-MM-DD`. */
  date: string
  /** Tokens dos arquivos-fonte inteiros ("sem RAGX"). */
  baseline: number
  /** Tokens que o RAGX entregou ("com RAGX"). */
  delivered: number
  calls: number
}

export interface SavingsSeries {
  /** Um item por dia, do mais antigo para hoje, dias sem uso com zero. */
  days: SavingsDay[]
  baseline: number
  delivered: number
  calls: number
}

/** `mcp`: ferramenta chamada por um agente; `cli`: comando de consulta no terminal; `session`: sessão do Claude aberta no projeto. */
export type ActivityKind = 'mcp' | 'cli' | 'session'

/** Uma linha de `.ragx/logs/mcp.jsonl` ou `cli.jsonl`, para a tela de atividade. Nunca a consulta. */
export interface ActivityEvent {
  /** Único e estável: projeto, arquivo e posição da linha. */
  id: string
  ts: string
  projectId: string
  projectName: string
  kind: ActivityKind
  /** Ferramenta MCP (`build_context`) ou comando (`search`, `session_start`). */
  name: string
  ms: number | null
  ok: boolean | null
  tokensDelivered: number | null
  baselineTokens: number | null
  /** `claude-code` quando quem chamou foi o Claude Code; `null` quando não dá para saber. */
  client: string | null
  /** Perfil do Claude Code (`padrão`, `empresa`...). */
  profile: string | null
  session: string | null
}

export interface TelemetrySummary {
  callsByTool: TelemetryCallCount[]
  totalCalls: number
  tokensDelivered: number
  /** Economia de tokens por dia (janela própria de `SAVINGS_DAYS`, não a de `sinceHours`). */
  savings?: SavingsSeries
  /** Maior `ts` de todas as linhas válidas do log, sem o filtro de `sinceHours`. `null` sem log. */
  lastCallAt: string | null
}

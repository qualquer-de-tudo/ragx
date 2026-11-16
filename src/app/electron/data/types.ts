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

/**
 * `mcp`: ferramenta chamada por um agente; `cli`: comando de consulta no terminal; `session`: sessão do Claude aberta no
 * projeto; `nudge`: o lembrete de busca do hook (Grep/Glob) foi mostrado, o que NÃO é uso do RAGX (ver `ragx-use.ts`).
 */
export type ActivityKind = 'mcp' | 'cli' | 'session' | 'nudge'

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
  /** Código do erro quando a chamada falhou (`not_found`, `rate_limited`...); `null` em sucesso ou em linha antiga. */
  errCode: string | null
  /** Tamanho da resposta no fio, em caracteres, e em tokens estimados (log v2 do servidor MCP). */
  respChars: number | null
  respTokens: number | null
  /** Cliente MCP que chamou (`claude-code`, `codex-mcp-client`...); `null` quando não dá para saber. */
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
  /**
   * O mesmo `lastCallAt`, por cliente MCP (`client` da linha). Linha sem `client` fica de fora: não dá para dizer que
   * foi o Claude Code. Opcional: snapshot antigo e testes não o têm.
   */
  lastCallByClient?: Record<string, string>
  /** Chamadas da janela `sinceHours` gravadas com `degraded: true` (a busca caiu para palavra-chave: embedder fora). */
  degradedCalls?: number
}

/** Um trecho do preview de `build_context` (RAGX-0187): sem `content`, o renderer nunca vê código. */
export interface ContextPreviewFragment {
  project: string | null
  documentPath: string
  lines: [number, number]
  symbol: string | null
  headingPath: string | null
  score: number
  tokens: number
  compressed: boolean
  strategy: string | null
  reason: string | null
}

/** O que o agente receberia para uma pergunta, já filtrado: sem `query` nem `content`. */
export interface ContextPreview {
  intent: string | null
  estimatedTokens: number
  budget: number
  fragments: ContextPreviewFragment[]
  /** O que ficou de fora, agrupado por motivo. */
  dropped: Array<{ why: string; count: number }>
}

/** Números de sessão do Claude Code (RAGX-0205): medianas ou totais. Resultados em caracteres. */
export interface UsageMetrics {
  turns: number
  prompts: number
  inputTokens: number
  cacheReadTokens: number
  cacheCreationTokens: number
  outputTokens: number
  totalTokens: number
  searchCalls: number
  readCalls: number
  ragxCalls: number
  otherCalls: number
  imageReads: number
  searchResultChars: number
  readResultChars: number
  ragxResultChars: number
}

export interface UsageGroup {
  sessions: number
  /** `null` quando o grupo não tem sessão: não há mediana. */
  median: UsageMetrics | null
  total: UsageMetrics
}

export interface UsageBlock {
  sessions: number
  firstAt: string | null
  lastAt: string | null
  all: UsageGroup
  withRagx: UsageGroup
  withoutRagx: UsageGroup
  adoption: { sessions: number; withRagx: number; hinted: number; reminded: number; ragxAfterReminder: number }
}

export interface UsageProject extends UsageBlock {
  /** Id do projeto no hub; `null` para um projeto fora do registro. */
  id: string | null
  name: string
}

/** `ragx usage --json` (RAGX-0205): consumo real lido das sessões do Claude Code. Observação, não experimento. */
export interface UsageReport {
  days: number
  since: string | null
  generatedAt: string | null
  charsPerToken: number
  sessionsScanned: number
  sessionsOutsideProjects: number
  overall: UsageBlock
  projects: UsageProject[]
}

/** Adoção (RAGX-0190): só contagens, datas e ids de projeto. `since` é o evento mais antigo realmente lido. */
export interface AdoptionSummary {
  since: string | null
  sessions: number
  withCalls: number
  withoutCalls: number
  unidentified: number
  callsWithoutStart: number
  byProject: Array<{ projectId: string; projectName: string; sessions: number; withCalls: number }>
}

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

export interface TelemetrySummary {
  callsByTool: TelemetryCallCount[]
  totalCalls: number
  tokensDelivered: number
}

import type { HubProject, ProjectStats, ProjectStatsUnavailable, TelemetrySummary } from '../../electron/data/types'

export interface ProjectSnapshot extends HubProject {
  stats: ProjectStats | ProjectStatsUnavailable
  telemetry: TelemetrySummary
}

export interface Snapshot {
  projects: ProjectSnapshot[]
  generatedAt: string
}

export interface RagxBridge {
  getSnapshot: () => Promise<Snapshot>
  onSnapshot: (cb: (snapshot: Snapshot) => void) => () => void
}

declare global {
  interface Window {
    ragx: RagxBridge
  }
}

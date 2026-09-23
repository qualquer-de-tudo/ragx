import type { HubProject, ProjectStats, ProjectStatsUnavailable, TelemetrySummary } from '../../electron/data/types'

export interface ProjectSnapshot extends HubProject {
  stats: ProjectStats | ProjectStatsUnavailable
  telemetry: TelemetrySummary
}

export interface Snapshot {
  projects: ProjectSnapshot[]
  generatedAt: string
}

export interface TrialResult {
  totals: {
    baseline_tokens: number
    ragx_tokens: number
    saved_ratio: number
    source_coverage: number
  }
}

export interface SecurityScanResult {
  root: string
  scanned: number
  blocked: Array<{ path: string; rule: string; severity: string; line: number; preview: string }>
  redacted: Array<{ path: string; findings: number }>
  skipped: number
  ruleset: { version: string; rules: number; disabled: string[] }
  policy: string
}

export interface RagxBridge {
  getSnapshot: () => Promise<Snapshot>
  onSnapshot: (cb: (snapshot: Snapshot) => void) => () => void
  runTrial: (projectPath: string) => Promise<TrialResult>
  runSecurityScan: (projectPath: string) => Promise<SecurityScanResult>
}

declare global {
  interface Window {
    ragx: RagxBridge
  }
}

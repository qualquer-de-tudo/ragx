import fs from 'node:fs'
import path from 'node:path'

export interface StatusFile {
  schema_version: 1
  written_at: string
  project: { id: string; name: string; root: string }
  index: {
    finished_at: string
    mode: string
    source: string
    branch: string | null
    commit: string | null
    dirty: boolean | null
  } | null
  counts: { documents: number; chunks: number; embeddings: number; pending_embeddings: number }
  embedding: { provider: string; model: string }
  hooks: { installed: boolean | null }
  running: { pid: number; op: string; source: string; started_at: string } | null
  pending: boolean
  last_error: string | null
}

export function readStatusFile(projectPath: string): StatusFile | null {
  try {
    const raw = fs.readFileSync(path.join(projectPath, '.ragx', 'status.json'), 'utf-8')
    const data = JSON.parse(raw) as StatusFile
    if (typeof data !== 'object' || data === null || data.schema_version !== 1) return null
    return data
  } catch {
    return null
  }
}

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { HubProject } from './types'

interface RawRegistry {
  schema_version: number
  projects: Array<{
    id: string
    name: string
    path: string | null
    cloned: number
    embedding_model: string | null
    visibility: string
    status: string
    chunks: number
    last_sync: string | null
  }>
}

function registryPath(): string {
  return path.join(os.homedir(), '.ragx', 'hub', 'registry.json')
}

export function readHubRegistry(): HubProject[] {
  const p = registryPath()
  if (!fs.existsSync(p)) return []

  const raw: RawRegistry = JSON.parse(fs.readFileSync(p, 'utf-8'))
  return raw.projects.map((proj) => ({
    id: proj.id,
    name: proj.name,
    path: proj.path,
    cloned: Boolean(proj.cloned),
    embeddingModel: proj.embedding_model,
    visibility: proj.visibility,
    status: proj.status,
    chunks: proj.chunks,
    lastSync: proj.last_sync,
  }))
}

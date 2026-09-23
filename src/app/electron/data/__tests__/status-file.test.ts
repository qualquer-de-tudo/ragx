import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { readStatusFile } from '../status-file'

function project(content?: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-status-'))
  if (content !== undefined) {
    fs.mkdirSync(path.join(dir, '.ragx'))
    fs.writeFileSync(path.join(dir, '.ragx', 'status.json'), content, 'utf-8')
  }
  return dir
}

const VALID = {
  schema_version: 1,
  written_at: '2026-09-23T12:00:00Z',
  project: { id: 'p', name: 'p', root: 'C:/p' },
  index: { finished_at: '2026-09-23T11:59:00Z', mode: 'incremental', source: 'cli', branch: 'main', commit: 'abc', dirty: false },
  counts: { documents: 4, chunks: 10, embeddings: 8, pending_embeddings: 2 },
  embedding: { provider: 'ollama', model: 'nomic-embed-text' },
  hooks: { installed: true },
  running: null,
  pending: false,
  last_error: null,
}

describe('readStatusFile', () => {
  it('lê o arquivo da Parte A', () => {
    const st = readStatusFile(project(JSON.stringify(VALID)))
    expect(st?.counts.pending_embeddings).toBe(2)
    expect(st?.index?.branch).toBe('main')
  })

  it('ausente, inválido ou de outra versão devolve null', () => {
    expect(readStatusFile(project())).toBeNull()
    expect(readStatusFile(project('{nao é json'))).toBeNull()
    expect(readStatusFile(project(JSON.stringify({ ...VALID, schema_version: 2 })))).toBeNull()
  })
})

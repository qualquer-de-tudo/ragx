import { describe, expect, it, vi, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

vi.mock('node:os', async (importOriginal) => {
  const actual = await importOriginal<typeof os>()
  // node:os expõe um `default` com cópias dos exports nomeados (para
  // interop CJS/ESM). Sob Node 25 + vitest 2.x, `import os from 'node:os'`
  // lê `os.homedir` a partir desse `default`, não do named export do topo —
  // então o mock precisa sobrescrever os dois com a MESMA referência de
  // vi.fn(), senão `import os from 'node:os'` continua vendo o homedir real.
  const homedir = vi.fn()
  return { ...actual, homedir, default: { ...(actual as unknown as { default: typeof os }).default, homedir } }
})

describe('readHubRegistry', () => {
  let tmpHome: string

  beforeEach(() => {
    tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-hub-test-'))
    vi.mocked(os.homedir).mockReturnValue(tmpHome)
  })

  it('retorna lista vazia quando o hub nao existe', async () => {
    const { readHubRegistry } = await import('../hub')
    expect(readHubRegistry()).toEqual([])
  })

  it('le e mapeia o registry.json existente', async () => {
    const hubDir = path.join(tmpHome, '.ragx', 'hub')
    fs.mkdirSync(hubDir, { recursive: true })
    fs.writeFileSync(
      path.join(hubDir, 'registry.json'),
      JSON.stringify({
        schema_version: 1,
        projects: [
          {
            id: 'abc123',
            name: 'meu-projeto',
            path: 'C:\\projects\\meu-projeto',
            cloned: 1,
            embedding_model: 'fastembed:x',
            visibility: 'workspace',
            status: 'ok',
            chunks: 42,
            last_sync: '2026-09-21T10:00:00Z',
          },
        ],
      }),
      'utf-8',
    )

    const { readHubRegistry } = await import('../hub')
    const result = readHubRegistry()
    expect(result).toEqual([
      {
        id: 'abc123',
        name: 'meu-projeto',
        path: 'C:\\projects\\meu-projeto',
        cloned: true,
        embeddingModel: 'fastembed:x',
        visibility: 'workspace',
        status: 'ok',
        chunks: 42,
        lastSync: '2026-09-21T10:00:00Z',
      },
    ])
  })
})

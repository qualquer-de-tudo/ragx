import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/** RAGX-0176: o painel lê `status.json`, nunca o banco. Quem quiser os números do índice pede à CLI. */
function sources(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' ? [] : sources(full)
    return e.name.endsWith('.ts') ? [full] : []
  })
}

describe('o painel não abre o knowledge.db', () => {
  const files = sources(path.resolve(__dirname, '..'))

  it('nenhum arquivo do processo principal importa um leitor de SQLite', () => {
    for (const f of files) expect(fs.readFileSync(f, 'utf8'), f).not.toMatch(/from 'sql\.js'|better-sqlite3|node:sqlite/)
  })

  it('nenhum arquivo que cita knowledge.db também lê arquivo', () => {
    for (const f of files) {
      const text = fs.readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '')
      if (text.includes('knowledge.db')) expect(text, f).not.toMatch(/readFile|createReadStream|openSync/)
    }
  })
})

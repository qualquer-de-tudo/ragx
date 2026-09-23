import { describe, expect, it, beforeAll, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import initSqlJsForFixture from 'sql.js'
import { initSqlWasm, readProjectStats } from '../project-stats'

describe('readProjectStats', () => {
  let projectPath: string

  beforeAll(async () => {
    await initSqlWasm()
  })

  beforeEach(() => {
    projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-project-stats-test-'))
  })

  it('retorna unavailable quando a pasta do projeto nao existe', () => {
    const missingPath = path.join(projectPath, 'nao-existe')
    const result = readProjectStats(missingPath)
    expect(result).toEqual({
      unavailable: true,
      reason: 'pasta do projeto não existe mais',
    })
  })

  it('retorna unavailable quando .ragx/knowledge.db nao existe', () => {
    const result = readProjectStats(projectPath)
    expect(result).toEqual({
      unavailable: true,
      reason: 'projeto ainda não foi indexado (.ragx/knowledge.db ausente)',
    })
  })

  it('conta documents, chunks e embeddings de um knowledge.db real', async () => {
    const ragxDir = path.join(projectPath, '.ragx')
    fs.mkdirSync(ragxDir, { recursive: true })

    const SQL = await initSqlJsForFixture()
    const fixtureDb = new SQL.Database()
    fixtureDb.run('CREATE TABLE documents (id INTEGER PRIMARY KEY)')
    fixtureDb.run('CREATE TABLE chunks (id INTEGER PRIMARY KEY)')
    fixtureDb.run('CREATE TABLE embeddings (id INTEGER PRIMARY KEY)')
    fixtureDb.run('INSERT INTO documents (id) VALUES (1), (2)')
    fixtureDb.run('INSERT INTO chunks (id) VALUES (1), (2), (3)')
    fixtureDb.run('INSERT INTO embeddings (id) VALUES (1), (2), (3), (4)')

    const bytes = fixtureDb.export()
    fixtureDb.close()
    fs.writeFileSync(path.join(ragxDir, 'knowledge.db'), Buffer.from(bytes))

    const result = readProjectStats(projectPath)
    expect(result).toEqual({ documents: 2, chunks: 3, embeddings: 4 })
  })
})

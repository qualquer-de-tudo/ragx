import fs from 'node:fs'
import path from 'node:path'
import initSqlJs, { type Database, type SqlJsStatic } from 'sql.js'
import type { ProjectStats, ProjectStatsUnavailable } from './types'

let SQL: SqlJsStatic | null = null

/**
 * Carrega o modulo WASM do sql.js uma unica vez. Deve ser chamado (e
 * aguardado) antes da primeira chamada a readProjectStats — normalmente
 * durante app.whenReady() no main process (Task 3).
 */
export async function initSqlWasm(): Promise<void> {
  if (SQL) return
  SQL = await initSqlJs()
}

export function readProjectStats(
  projectPath: string,
): ProjectStats | ProjectStatsUnavailable {
  if (!fs.existsSync(projectPath)) {
    return { unavailable: true, reason: 'pasta do projeto não existe mais' }
  }
  const dbPath = path.join(projectPath, '.ragx', 'knowledge.db')
  if (!fs.existsSync(dbPath)) {
    return { unavailable: true, reason: 'projeto ainda não foi indexado (.ragx/knowledge.db ausente)' }
  }
  if (!SQL) {
    return { unavailable: true, reason: 'leitor SQLite (sql.js) ainda não foi inicializado' }
  }

  const fileBuffer = fs.readFileSync(dbPath)
  let db: Database | null = null
  try {
    db = new SQL.Database(fileBuffer)
    const documents = _count(db, 'documents')
    const chunks = _count(db, 'chunks')
    const embeddings = _count(db, 'embeddings')
    return { documents, chunks, embeddings }
  } finally {
    db?.close()
  }
}

function _count(db: Database, table: string): number {
  const result = db.exec(`SELECT COUNT(*) AS n FROM ${table}`)
  return (result[0]?.values[0]?.[0] as number) ?? 0
}

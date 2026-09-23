import fs from 'node:fs'
import path from 'node:path'
import initSqlJs, { type Database, type SqlJsStatic } from 'sql.js'
import type { ProjectStats, ProjectStatsUnavailable } from './types'

let SQL: SqlJsStatic | null = null

/**
 * Carrega o modulo WASM do sql.js uma unica vez. Deve ser chamado (e
 * aguardado) antes da primeira chamada a readProjectStats — normalmente
 * durante app.whenReady() no main process (Task 3).
 *
 * `locateFile` é necessário porque o lookup padrão do sql.js assume que o
 * `.wasm` está ao lado do seu próprio JS em `node_modules/sql.js/dist/` —
 * verdade em dev, mas não garantido depois de empacotado num asar.
 * `require.resolve` funciona nos dois casos: em dev resolve o caminho normal
 * em `node_modules`; empacotado, resolve o caminho "dentro" do asar, que o
 * `fs` do Electron redireciona de forma transparente para
 * `app.asar.unpacked/` quando o arquivo está listado em `asarUnpack`
 * (ver `electron-builder.yml`).
 */
export async function initSqlWasm(): Promise<void> {
  if (SQL) return
  SQL = await initSqlJs({
    locateFile: (file) => require.resolve(`sql.js/dist/${file}`),
  })
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

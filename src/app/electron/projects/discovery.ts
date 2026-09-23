import fs from 'node:fs'
import path from 'node:path'

export interface Found {
  path: string
  name: string
  alreadyRegistered: boolean
}

export interface DirEntryLike {
  name: string
  isDirectory: boolean
}

export interface DiscoverOpts {
  /** Profundidade máxima de descida abaixo da raiz. Padrão 4. */
  maxDepth?: number
  readdir?: (dir: string) => DirEntryLike[]
  exists?: (p: string) => boolean
}

/** Pastas que nunca escondem um projeto do usuário - só ruído/dependências/artefatos de build. */
const SKIP_DIRS: ReadonlySet<string> = new Set(['node_modules', '.git', '.venv', 'venv', 'dist', 'build', '.ragx', 'target'])

function defaultReaddir(dir: string): DirEntryLike[] {
  try {
    return fs.readdirSync(dir, { withFileTypes: true }).map((e) => ({ name: e.name, isDirectory: e.isDirectory() }))
  } catch {
    // Erro de permissão (ou a pasta sumiu entre a listagem do pai e agora):
    // ignora essa pasta em vez de derrubar a busca inteira.
    return []
  }
}

function normalizeForCompare(p: string): string {
  // `registeredPaths` compara sem diferenciar maiúsculas só no Windows -
  // noutro SO, caminhos com letra diferente são pastas diferentes de verdade.
  return process.platform === 'win32' ? p.toLowerCase() : p
}

/**
 * Procura `ragx.toml` a partir de `root`, até `maxDepth` níveis abaixo (a
 * própria raiz conta como nível 0). Não desce dentro de uma pasta onde já
 * achou um projeto (um `ragx.toml` aninhado dentro de outro projeto - ex.:
 * um vendored/submodule - nunca aparece). Pastas de dependência/build
 * (`SKIP_DIRS`) nunca são visitadas. Erros de leitura (permissão, pasta
 * removida) são ignorados por pasta, não interrompem a busca.
 */
export function discoverProjects(root: string, registeredPaths: Set<string>, opts: DiscoverOpts = {}): Found[] {
  const maxDepth = opts.maxDepth ?? 4
  const readdir = opts.readdir ?? defaultReaddir
  const exists = opts.exists ?? ((p: string) => fs.existsSync(p))

  const registeredNormalized = new Set(Array.from(registeredPaths).map(normalizeForCompare))

  if (!exists(root)) return []

  const results: Found[] = []

  function walk(dir: string, depth: number): void {
    let entries: DirEntryLike[]
    try {
      entries = readdir(dir)
    } catch {
      // Erro de permissão (ou pasta removida entre a listagem do pai e
      // agora), inclusive vindo de um `readdir` injetado por teste: ignora
      // essa pasta em vez de derrubar a busca inteira.
      return
    }

    const hasRagxToml = entries.some((e) => !e.isDirectory && e.name === 'ragx.toml')
    if (hasRagxToml) {
      results.push({
        path: dir,
        name: path.basename(dir),
        alreadyRegistered: registeredNormalized.has(normalizeForCompare(dir)),
      })
      return // não desce dentro de um projeto já encontrado
    }

    if (depth >= maxDepth) return

    for (const entry of entries) {
      if (!entry.isDirectory) continue
      if (SKIP_DIRS.has(entry.name)) continue
      walk(path.join(dir, entry.name), depth + 1)
    }
  }

  walk(root, 0)

  return results.sort((a, b) => a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' }))
}

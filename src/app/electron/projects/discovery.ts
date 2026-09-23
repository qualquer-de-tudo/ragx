import fs from 'node:fs'
import path from 'node:path'

export interface Found {
  path: string
  name: string
  alreadyRegistered: boolean
  /** Repositório git sem `ragx.toml`: candidato a projeto novo. */
  isNew: boolean
}

export interface DiscoverResult {
  items: Found[]
  /** `true` quando `maxDirs` foi atingido antes de terminar a busca - a lista pode estar incompleta. */
  truncated: boolean
}

export interface DirEntryLike {
  name: string
  isDirectory: boolean
}

export interface DiscoverOpts {
  /** Profundidade máxima de descida abaixo da raiz. Padrão 4. */
  maxDepth?: number
  /**
   * Orçamento de pastas visitadas (uma leitura de diretório cada). Escolher
   * `C:\` sem isso caminha dezenas de milhares de pastas e congela a janela
   * (Fix round 1 - `C:\` real: 44.600 pastas em ~11s). Padrão 5000.
   */
  maxDirs?: number
  readdir?: (dir: string) => DirEntryLike[]
  exists?: (p: string) => boolean
}

const DEFAULT_MAX_DIRS = 5000

/**
 * Pastas que nunca escondem um projeto do usuário - ruído/dependências/
 * artefatos de build, mais o ruído do próprio Windows quando a raiz
 * escolhida é ampla demais (`C:\`, a pasta do usuário). Comparado sem
 * diferenciar maiúsculas (Fix round 1).
 */
const SKIP_DIRS_LOWER: ReadonlySet<string> = new Set(
  [
    'node_modules',
    '.git',
    '.venv',
    'venv',
    'dist',
    'build',
    '.ragx',
    'target',
    'appdata',
    'windows',
    '$recycle.bin',
    'system volume information',
    'program files',
    'program files (x86)',
    'programdata',
  ].map((s) => s.toLowerCase()),
)

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
 * própria raiz conta como nível 0), sem visitar mais que `maxDirs` pastas
 * no total - a busca para e `truncated` vira `true` (a lista pode estar
 * incompleta, mas a chamada sempre devolve rápido). Uma pasta com `.git`
 * (diretório, ou arquivo no caso de worktree/submódulo) e sem `ragx.toml`
 * também entra, como candidato novo (`isNew`): numa máquina nova, é isso que
 * deixa escolher os repositórios um a um em vez de um projeto gigante com a
 * pasta inteira. Não desce dentro de uma pasta onde já achou um projeto ou
 * repositório (um `ragx.toml` aninhado dentro de outro projeto - ex.: um
 * vendored/submodule - nunca aparece). Pastas de
 * dependência/build/ruído do Windows (`SKIP_DIRS_LOWER`) nunca são
 * visitadas. Erros de leitura (permissão, pasta removida) são ignorados por
 * pasta, não interrompem a busca.
 */
export function discoverProjects(root: string, registeredPaths: Set<string>, opts: DiscoverOpts = {}): DiscoverResult {
  const maxDepth = opts.maxDepth ?? 4
  const maxDirs = opts.maxDirs ?? DEFAULT_MAX_DIRS
  const readdir = opts.readdir ?? defaultReaddir
  const exists = opts.exists ?? ((p: string) => fs.existsSync(p))

  const registeredNormalized = new Set(Array.from(registeredPaths).map(normalizeForCompare))

  if (!exists(root)) return { items: [], truncated: false }

  const results: Found[] = []
  let dirsVisited = 0
  let truncated = false

  function walk(dir: string, depth: number): void {
    if (truncated) return
    if (dirsVisited >= maxDirs) {
      truncated = true
      return
    }
    dirsVisited += 1

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
    const isGitRepo = entries.some((e) => e.name === '.git')
    if (hasRagxToml || isGitRepo) {
      results.push({
        path: dir,
        name: path.basename(dir),
        alreadyRegistered: registeredNormalized.has(normalizeForCompare(dir)),
        isNew: !hasRagxToml,
      })
      return // não desce dentro de um projeto (ou repositório) já encontrado
    }

    if (depth >= maxDepth) return

    for (const entry of entries) {
      if (truncated) return
      if (!entry.isDirectory) continue
      if (SKIP_DIRS_LOWER.has(entry.name.toLowerCase())) continue
      walk(path.join(dir, entry.name), depth + 1)
    }
  }

  walk(root, 0)

  return {
    items: results.sort((a, b) => a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' })),
    truncated,
  }
}

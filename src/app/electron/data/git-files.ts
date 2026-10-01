/**
 * Branch e commit de um projeto lidos DIRETO dos arquivos do git, sem criar processo (RAGX-0172).
 *
 * O painel consultava `git rev-parse HEAD` e `git symbolic-ref` por projeto a cada snapshot (a cada 5 s):
 * ~290 processos por minuto com 12 projetos. O que ele quer saber mora em arquivos de texto pequenos
 * (`.git/HEAD`, `.git/refs/heads/<ramo>`, `.git/packed-refs`), e ler arquivo não cria processo.
 *
 * Só METADADO: nenhum conteúdo de código, nenhum objeto do git, nenhum estado sujo. Qualquer dúvida
 * (formato desconhecido, `reftable`, ref simbólica encadeada, arquivo ilegível, hash estranho) devolve
 * `'unsupported'` e quem chama cai no `git`, como antes. Nunca lança.
 */
import fs from 'node:fs'
import path from 'node:path'

export interface GitHead {
  branch: string | null
  commit: string
}

export type GitFilesResult = GitHead | null | 'unsupported'

/** O que a leitura precisa do sistema de arquivos (injetável para teste). */
export interface GitFs {
  /** Texto do arquivo (até `maxBytes`), `null` se não existe; lança se for grande demais ou ilegível. */
  readText: (file: string, maxBytes: number) => string | null
  stat: (file: string) => { mtimeMs: number; size: number; isDirectory: boolean; isFile: boolean } | null
}

const MAX_BYTES = 64 * 1024
const HASH = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/

export const realGitFs: GitFs = {
  readText: (file, maxBytes) => {
    let st: fs.Stats
    try {
      st = fs.statSync(file)
    } catch {
      return null
    }
    if (!st.isFile()) return null
    if (st.size > maxBytes) throw new Error('arquivo grande demais')
    return fs.readFileSync(file, 'utf-8')
  },
  stat: (file) => {
    try {
      const st = fs.statSync(file)
      return { mtimeMs: st.mtimeMs, size: st.size, isDirectory: st.isDirectory(), isFile: st.isFile() }
    } catch {
      return null
    }
  },
}

const clean = (text: string): string => text.replace(/\r?\n$/, '').replace(/\r$/, '').trim()

/** `ref:` seguro: relativo, sem `..` e sem barra invertida. */
function safeRef(ref: string): boolean {
  if (!ref || ref.startsWith('/') || /^[A-Za-z]:/.test(ref)) return false
  return !ref.split('/').some((part) => part === '..' || part === '' || part === '.') && !ref.includes('\\')
}

interface Resolved {
  gitDir: string
  commonDir: string
}

/** Sobe a partir do projeto até achar `.git` (pasta, ou arquivo `gitdir:` de worktree/submódulo). */
function findGitDir(projectPath: string, io: GitFs): Resolved | null | 'unsupported' {
  let dir = path.resolve(projectPath)
  for (;;) {
    const dotGit = path.join(dir, '.git')
    const st = io.stat(dotGit)
    if (st) {
      let gitDir: string
      if (st.isDirectory) {
        gitDir = dotGit
      } else if (st.isFile) {
        const text = io.readText(dotGit, MAX_BYTES)
        const m = text === null ? null : /^gitdir:\s*(.+)$/m.exec(text)
        if (!m) return 'unsupported'
        gitDir = path.resolve(dir, m[1].trim().replace(/\\/g, '/'))
      } else {
        return 'unsupported'
      }
      // worktree: `HEAD` fica em `gitDir`, as refs em `commondir`
      const common = io.readText(path.join(gitDir, 'commondir'), MAX_BYTES)
      const commonDir = common === null ? gitDir : path.resolve(gitDir, clean(common).replace(/\\/g, '/'))
      return { gitDir, commonDir }
    }
    const parent = path.dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
}

function packedRef(commonDir: string, ref: string, io: GitFs): string | null {
  const text = io.readText(path.join(commonDir, 'packed-refs'), MAX_BYTES)
  if (text === null) return null
  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith('#') || line.startsWith('^')) continue
    const space = line.indexOf(' ')
    if (space < 0) continue
    if (line.slice(space + 1).trim() === ref) return line.slice(0, space)
  }
  return null
}

/** O arquivo de ref solto (se existir) e o que o `HEAD` diz: usado também pela assinatura do cache. */
export function readGitHeadFromFiles(projectPath: string, io: GitFs = realGitFs): GitFilesResult {
  try {
    if (io.stat(projectPath) === null) return 'unsupported' // pasta que nem existe: deixa o `git` responder
    const found = findGitDir(projectPath, io)
    if (found === null || found === 'unsupported') return found
    const { gitDir, commonDir } = found

    // `reftable` guarda as refs em outro formato: aqui não dá para ler
    if (io.stat(path.join(commonDir, 'reftable'))?.isDirectory) return 'unsupported'
    const config = io.readText(path.join(commonDir, 'config'), MAX_BYTES)
    if (config !== null && /refstorage\s*=\s*reftable/i.test(config)) return 'unsupported'

    const headText = io.readText(path.join(gitDir, 'HEAD'), MAX_BYTES)
    if (headText === null) return 'unsupported'
    const head = clean(headText)
    if (!head) return 'unsupported' // acabou de ser reescrito pelo git

    if (!head.startsWith('ref:')) {
      return HASH.test(head) ? { branch: null, commit: head } : 'unsupported' // HEAD destacado
    }
    const ref = head.slice(4).trim()
    if (!safeRef(ref) || !ref.startsWith('refs/')) return 'unsupported'

    const loose = io.readText(path.join(commonDir, ...ref.split('/')), MAX_BYTES)
    let commit: string | null = null
    if (loose !== null) {
      const value = clean(loose)
      if (value.startsWith('ref:')) return 'unsupported' // ref simbólica encadeada
      commit = value
    } else {
      commit = packedRef(commonDir, ref, io)
    }
    if (commit === null) return null // ramo sem commit ainda (repositório recém-criado)
    if (!HASH.test(commit)) return 'unsupported'
    const branch = ref.startsWith('refs/heads/') ? ref.slice('refs/heads/'.length) : null
    return { branch, commit }
  } catch {
    return 'unsupported'
  }
}

// -- cache por projeto -----------------------------------------------------

interface Signature {
  head: string
  ref: string
  packed: string
}

interface CacheEntry {
  signature: Signature
  value: GitFilesResult
  gitDir: string
  commonDir: string
  refPath: string | null
}

const cache = new Map<string, CacheEntry>()

const sig = (file: string, io: GitFs): string => {
  const st = io.stat(file)
  return st ? `${st.mtimeMs}:${st.size}` : '-'
}

/**
 * Como `readGitHeadFromFiles`, com cache: com `HEAD`, o arquivo da ref e `packed-refs` iguais (mtime e
 * tamanho), devolve o MESMO objeto (identidade estável, que a RAGX-0175 usa para não re-renderizar).
 */
export function readGitHeadCached(projectPath: string, io: GitFs = realGitFs): GitFilesResult {
  const key = path.resolve(projectPath)
  const hit = cache.get(key)
  if (hit && hit.value !== 'unsupported') {
    const signature: Signature = {
      head: sig(path.join(hit.gitDir, 'HEAD'), io),
      ref: hit.refPath ? sig(hit.refPath, io) : '-',
      packed: sig(path.join(hit.commonDir, 'packed-refs'), io),
    }
    if (signature.head === hit.signature.head && signature.ref === hit.signature.ref && signature.packed === hit.signature.packed) {
      return hit.value
    }
  }
  const value = readGitHeadFromFiles(projectPath, io)
  if (value === 'unsupported' || value === null) {
    cache.delete(key)
    return value
  }
  const found = findGitDir(projectPath, io)
  if (found === null || found === 'unsupported') return value
  const refPath = refPathOf(found.gitDir, found.commonDir, io)
  cache.set(key, {
    value,
    gitDir: found.gitDir,
    commonDir: found.commonDir,
    refPath,
    signature: {
      head: sig(path.join(found.gitDir, 'HEAD'), io),
      ref: refPath ? sig(refPath, io) : '-',
      packed: sig(path.join(found.commonDir, 'packed-refs'), io),
    },
  })
  return value
}

function refPathOf(gitDir: string, commonDir: string, io: GitFs): string | null {
  try {
    const text = io.readText(path.join(gitDir, 'HEAD'), MAX_BYTES)
    if (text === null) return null
    const head = clean(text)
    if (!head.startsWith('ref:')) return null
    const ref = head.slice(4).trim()
    return safeRef(ref) ? path.join(commonDir, ...ref.split('/')) : null
  } catch {
    return null
  }
}

/** Para teste. */
export function resetGitCache(): void {
  cache.clear()
}

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

/**
 * O pacote que o `.exe` leva em `resources/ragx-bundle/`: o `uv.exe`, o wheel
 * do RAGX e o `bundle.json` com os hashes de ambos. Quem gera é
 * `scripts/prepare-bundle.mjs`; aqui só se lê e se confere.
 *
 * O hash protege contra download corrompido, não contra adulteração (o
 * `bundle.json` viaja no mesmo pacote): isso só a assinatura de código cobre.
 */
export interface BundleInfo {
  dir: string
  uvPath: string
  wheelPath: string
  version: string
  python: string
}

export class BundleError extends Error {
  constructor(
    readonly code: 'missing' | 'hash',
    message: string,
  ) {
    super(message)
  }
}

interface BundleDeps {
  /** `process.resourcesPath` do app empacotado. */
  resourcesPath?: string
  /** Pasta usada em desenvolvimento (`src/app/resources/ragx-bundle`). */
  devDir?: string
  exists?: (p: string) => boolean
  readFile?: (p: string) => string
  sha256File?: (p: string) => string
}

const sha256OfFile = (p: string): string => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')

export function findBundleDir(deps: BundleDeps = {}): string | null {
  const exists = deps.exists ?? ((p: string) => fs.existsSync(p))
  const resourcesPath = deps.resourcesPath ?? (process as NodeJS.Process & { resourcesPath?: string }).resourcesPath
  const devDir = deps.devDir ?? path.join(__dirname, '..', '..', 'resources', 'ragx-bundle')
  const candidates = [resourcesPath ? path.join(resourcesPath, 'ragx-bundle') : null, devDir]
  for (const dir of candidates) {
    if (dir !== null && exists(path.join(dir, 'bundle.json'))) return dir
  }
  return null
}

interface RawBundle {
  version?: unknown
  python?: unknown
  uv?: { file?: unknown; sha256?: unknown }
  wheel?: { file?: unknown; sha256?: unknown }
}

const isNonEmpty = (v: unknown): v is string => typeof v === 'string' && v.length > 0

/** Lê o pacote e confere os hashes. Lança `BundleError`; nunca devolve um pacote não conferido. */
export function loadBundle(deps: BundleDeps = {}): BundleInfo {
  const exists = deps.exists ?? ((p: string) => fs.existsSync(p))
  const readFile = deps.readFile ?? ((p: string) => fs.readFileSync(p, 'utf-8'))
  const sha256File = deps.sha256File ?? sha256OfFile

  const dir = findBundleDir(deps)
  if (dir === null) throw new BundleError('missing', 'pacote de instalação do RAGX não encontrado')

  let raw: RawBundle
  try {
    raw = JSON.parse(readFile(path.join(dir, 'bundle.json'))) as RawBundle
  } catch {
    throw new BundleError('missing', 'bundle.json ilegível')
  }
  if (
    !isNonEmpty(raw.version) ||
    !isNonEmpty(raw.python) ||
    !isNonEmpty(raw.uv?.file) ||
    !isNonEmpty(raw.uv?.sha256) ||
    !isNonEmpty(raw.wheel?.file) ||
    !isNonEmpty(raw.wheel?.sha256)
  ) {
    throw new BundleError('missing', 'bundle.json incompleto')
  }

  // `basename`: o nome vem de um arquivo de dados e nunca pode sair da pasta do pacote.
  const uvPath = path.join(dir, path.basename(raw.uv.file))
  const wheelPath = path.join(dir, path.basename(raw.wheel.file))
  for (const [p, expected] of [
    [uvPath, raw.uv.sha256],
    [wheelPath, raw.wheel.sha256],
  ] as const) {
    if (!exists(p)) throw new BundleError('missing', `arquivo ausente no pacote: ${path.basename(p)}`)
    if (sha256File(p).toLowerCase() !== expected.toLowerCase()) {
      throw new BundleError('hash', `hash diferente do esperado: ${path.basename(p)}`)
    }
  }
  return { dir, uvPath, wheelPath, version: raw.version, python: raw.python }
}

/** Caminho do `uv.exe` do pacote (sem conferir hash: o catálogo já conferiu ao montar o job). */
export function uvCommand(deps: BundleDeps = {}): string {
  const dir = findBundleDir(deps)
  if (dir === null) return 'uv'
  const readFile = deps.readFile ?? ((p: string) => fs.readFileSync(p, 'utf-8'))
  try {
    const raw = JSON.parse(readFile(path.join(dir, 'bundle.json'))) as RawBundle
    if (isNonEmpty(raw.uv?.file)) return path.join(dir, path.basename(raw.uv.file))
  } catch {
    // cai no `uv` puro; o job já teria sido recusado por `loadBundle`
  }
  return 'uv'
}

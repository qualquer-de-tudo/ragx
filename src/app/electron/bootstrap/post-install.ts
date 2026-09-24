import path from 'node:path'
import { ensureUserPath, type PathDeps } from './path-user'

export interface PostInstallDeps {
  /** Esquece o cache do caminho do `ragx` (o executável acabou de aparecer no disco). */
  resetCache: () => void
  resolveRagx: () => string | null
  pathDeps: PathDeps
}

export interface PostInstallResult {
  /** `false` se o `ragx.exe` não apareceu: a instalação não fez efeito. */
  found: boolean
  pathAdded: boolean
}

/**
 * Depois do `ragx-install`: refaz a resolução do executável e garante a pasta
 * dele no PATH do usuário, para terminais novos acharem o `ragx`. O painel em
 * si usa o caminho absoluto e não depende disso.
 */
export async function afterRagxInstall(deps: PostInstallDeps): Promise<PostInstallResult> {
  deps.resetCache()
  const exe = deps.resolveRagx()
  if (exe === null) return { found: false, pathAdded: false }
  const { added } = await ensureUserPath(path.dirname(exe), deps.pathDeps)
  return { found: true, pathAdded: added }
}

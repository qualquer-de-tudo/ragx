import fs from 'node:fs'
import path from 'node:path'

let cached: string | null | undefined

export function resetRagxCache(): void {
  cached = undefined
}

interface Deps {
  env?: NodeJS.ProcessEnv
  exists?: (p: string) => boolean
  platform?: NodeJS.Platform
}

/**
 * O app aberto pelo menu Iniciar herda o PATH do Explorer, que pode não ter
 * a pasta onde o instalador do RAGX pôs o executável. Por isso, além do PATH,
 * olha os locais conhecidos de instalação (uv tool / pipx).
 */
export function resolveRagx(deps: Deps = {}): string | null {
  const env = deps.env ?? process.env
  const exists = deps.exists ?? ((p: string) => fs.existsSync(p))
  const platform = deps.platform ?? process.platform
  const win = platform === 'win32'
  const sep = win ? ';' : ':'
  // `spawn`/`execFile` sem shell (obrigatório pelo plano) não conseguem
  // lançar `.cmd`/`.bat` diretamente - só `.exe` é um executável de verdade
  // no Windows. `PATHEXT` é ignorado de propósito.
  const names = win ? ['ragx.exe'] : ['ragx']

  for (const rawDir of (env.PATH ?? env.Path ?? '').split(sep).filter(Boolean)) {
    // `"C:\Program Files\x"` (aspas ao redor de segmentos com espaço) é comum
    // em PATH montado manualmente por instaladores; sem isso o `path.join`
    // gera um caminho com aspas literais que nunca existe.
    const dir = rawDir.replace(/^"(.*)"$/, '$1')
    for (const name of names) {
      const candidate = path.join(dir, name)
      if (exists(candidate)) return candidate
    }
  }
  const home = win ? env.USERPROFILE : env.HOME
  if (home) {
    const candidate = path.join(home, '.local', 'bin', win ? 'ragx.exe' : 'ragx')
    if (exists(candidate)) return candidate
  }
  return null
}

export function ragxCommand(): string {
  if (cached === undefined) cached = resolveRagx()
  return cached ?? 'ragx'
}

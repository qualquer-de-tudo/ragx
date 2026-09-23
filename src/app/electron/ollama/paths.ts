import fs from 'node:fs'
import path from 'node:path'

let cached: string | null | undefined

export function resetOllamaCache(): void {
  cached = undefined
}

interface Deps {
  env?: NodeJS.ProcessEnv
  exists?: (p: string) => boolean
  platform?: NodeJS.Platform
}

/**
 * O app aberto pelo menu Iniciar herda o PATH do Explorer, que pode não ter
 * a pasta do Ollama recém-instalado. Por isso, além do PATH, olha os locais
 * conhecidos de instalação. Mesmo padrão de `resolveRagx`: só `.exe` no
 * Windows (sem shell não dá para lançar `.cmd`) e segmentos do PATH sem aspas.
 */
export function resolveOllama(deps: Deps = {}): string | null {
  const env = deps.env ?? process.env
  const exists = deps.exists ?? ((p: string) => fs.existsSync(p))
  const platform = deps.platform ?? process.platform
  const win = platform === 'win32'
  const sep = win ? ';' : ':'
  const name = win ? 'ollama.exe' : 'ollama'

  for (const rawDir of (env.PATH ?? env.Path ?? '').split(sep).filter(Boolean)) {
    const dir = rawDir.replace(/^"(.*)"$/, '$1')
    const candidate = path.join(dir, name)
    if (exists(candidate)) return candidate
  }

  const fallbacks: string[] = []
  if (win) {
    if (env.LOCALAPPDATA) fallbacks.push(path.join(env.LOCALAPPDATA, 'Programs', 'Ollama', name))
  } else {
    fallbacks.push(path.join('/usr/local/bin', name), path.join('/opt/homebrew/bin', name))
  }
  for (const candidate of fallbacks) {
    if (exists(candidate)) return candidate
  }
  return null
}

/** Caminho resolvido (com cache) ou o nome nu `ollama`, que confia no PATH. */
export function ollamaCommand(): string {
  if (cached === undefined) cached = resolveOllama()
  return cached ?? 'ollama'
}

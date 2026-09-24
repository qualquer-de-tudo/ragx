import path from 'node:path'
import type { ExecFn } from '../system/exec'

export interface UninstallOptions {
  /** Também apaga o hub do usuário (`~/.ragx`). Nunca as pastas `.ragx/` dos projetos. */
  removeData: boolean
}

export interface UninstallDeps {
  exec: ExecFn
  /** Caminho do `ragx.exe` instalado, ou `null` se não houver. */
  ragxPath: () => string | null
  /** `uv.exe` do pacote do painel. */
  uvPath: () => string
  removeFromPath: () => Promise<{ removed: boolean }>
  rm: (p: string) => Promise<void>
  homedir: string
}

export interface UninstallResult {
  steps: string[]
  errors: string[]
}

const STEP_TIMEOUT_MS = 120_000

/**
 * Desfaz o que o `ragx-install` fez, nesta ordem: registro do MCP (precisa do
 * `ragx` ainda instalado), a ferramenta `ragx`, o PATH e, só se pedido, o hub.
 * Cada passo que falha vira um item em `errors` e os seguintes ainda rodam: um
 * `ragx.exe` travado não pode deixar o PATH e os configs de MCP para trás.
 */
export async function uninstallCli(opts: UninstallOptions, deps: UninstallDeps): Promise<UninstallResult> {
  const steps: string[] = []
  const errors: string[] = []

  const ragx = deps.ragxPath()
  if (ragx === null) {
    steps.push('ragx não está instalado: registro do MCP não precisa ser desfeito')
  } else {
    const r = await deps.exec(ragx, ['mcp', 'uninstall'], { timeoutMs: STEP_TIMEOUT_MS })
    if (r.code === 0) steps.push('registro do MCP removido dos clientes')
    else errors.push(`ragx mcp uninstall falhou: ${(r.stderr || r.stdout).trim().slice(0, 300)}`)
  }

  const uv = await deps.exec(deps.uvPath(), ['tool', 'uninstall', 'ragx'], { timeoutMs: STEP_TIMEOUT_MS })
  if (uv.code === 0) steps.push('ferramenta ragx removida')
  else if (/not installed|is not installed/i.test(uv.stderr + uv.stdout)) steps.push('ferramenta ragx já não estava instalada')
  else errors.push(`uv tool uninstall ragx falhou (feche o Claude Code e tente de novo): ${uv.stderr.trim().slice(0, 300)}`)

  try {
    const p = await deps.removeFromPath()
    steps.push(p.removed ? 'pasta removida do PATH' : 'PATH não foi alterado por este app: mantido')
  } catch (err) {
    errors.push(`não consegui ajustar o PATH: ${err instanceof Error ? err.message : String(err)}`)
  }

  if (opts.removeData) {
    const hub = path.join(deps.homedir, '.ragx')
    // Defesa contra um `homedir` vazio ou relativo: `rm` de `.ragx` cairia no
    // diretório de trabalho de quem chamou. Só apaga caminho absoluto.
    if (!path.isAbsolute(hub) || path.basename(hub) !== '.ragx') {
      errors.push('caminho do hub inesperado; nada apagado')
    } else {
      try {
        await deps.rm(hub)
        steps.push('dados do hub removidos')
      } catch (err) {
        errors.push(`não consegui remover ${hub}: ${err instanceof Error ? err.message : String(err)}`)
      }
    }
  }

  return { steps, errors }
}

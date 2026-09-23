import fs from 'node:fs'
import path from 'node:path'

export interface PanelSettings {
  onboardingDone: boolean
}

const FILE_NAME = 'settings.json'

const DEFAULT_SETTINGS: PanelSettings = { onboardingDone: false }

function filePath(dir: string): string {
  return path.join(dir, FILE_NAME)
}

/** Nunca lança: `dir` inexistente, arquivo ausente ou JSON corrompido viram as configurações padrão. */
export function readSettings(dir: string): PanelSettings {
  try {
    const raw = fs.readFileSync(filePath(dir), 'utf-8')
    const parsed = JSON.parse(raw) as Partial<PanelSettings>
    return { onboardingDone: parsed.onboardingDone === true }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

/**
 * Escrita atômica: grava num arquivo temporário e troca com `renameSync`
 * (operação atômica no mesmo volume), para nunca deixar `settings.json`
 * meio escrito se o processo morrer no meio do caminho. Se o `renameSync`
 * falhar (ex.: `target` travado por outro processo), remove o temporário
 * antes de propagar o erro - senão ele fica pra sempre em `dir` (Fix round 1).
 */
export function writeSettings(dir: string, s: PanelSettings): void {
  fs.mkdirSync(dir, { recursive: true })
  const target = filePath(dir)
  const tmp = path.join(dir, `.${FILE_NAME}.${process.pid}.${Date.now()}.tmp`)
  fs.writeFileSync(tmp, JSON.stringify(s, null, 2), 'utf-8')
  try {
    fs.renameSync(tmp, target)
  } catch (err) {
    try {
      fs.rmSync(tmp, { force: true })
    } catch {
      // limpeza best-effort - o erro original (a falha do rename) importa mais.
    }
    throw err
  }
}

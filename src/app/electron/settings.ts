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
 * meio escrito se o processo morrer no meio do caminho.
 */
export function writeSettings(dir: string, s: PanelSettings): void {
  fs.mkdirSync(dir, { recursive: true })
  const target = filePath(dir)
  const tmp = path.join(dir, `.${FILE_NAME}.${process.pid}.${Date.now()}.tmp`)
  fs.writeFileSync(tmp, JSON.stringify(s, null, 2), 'utf-8')
  fs.renameSync(tmp, target)
}

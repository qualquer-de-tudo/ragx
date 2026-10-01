import fs from 'node:fs'
import path from 'node:path'

/** Moedas aceitas no preço informado pela pessoa (RAGX-0186). */
export const CURRENCIES = ['BRL', 'USD', 'EUR'] as const
export type Currency = (typeof CURRENCIES)[number]

/** Preço por 1 milhão de tokens de ENTRADA, informado pela pessoa: o RAGX não embute tabela de preços. */
export interface Pricing {
  currency: Currency
  perMTokInput: number
}

export const MAX_PRICE = 10_000

/** Moeda do conjunto, preço finito e `0 < preço <= 10000`. Qualquer outra coisa é `null`. */
export function parsePricing(raw: unknown): Pricing | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
  const { currency, perMTokInput } = raw as { currency?: unknown; perMTokInput?: unknown }
  if (typeof currency !== 'string' || !(CURRENCIES as readonly string[]).includes(currency)) return null
  if (typeof perMTokInput !== 'number' || !Number.isFinite(perMTokInput) || perMTokInput <= 0 || perMTokInput > MAX_PRICE) return null
  return { currency: currency as Currency, perMTokInput }
}

/** O que o renderer vê de `getSettings()`: nada além disso sai do processo principal. */
export interface RendererSettings {
  onboardingDone: boolean
  /** Ausente por padrão: sem preço, nenhuma tela mostra valor em dinheiro. */
  pricing?: Pricing
  /** Ícone na bandeja com o estado geral (RAGX-0191). Ausente = desligado. */
  tray?: boolean
  /** Notificação do sistema quando um índice continua defasado (RAGX-0191). Ausente = desligado. */
  notifyStale?: boolean
  /** Atualização do painel pelo GitHub Releases (RAGX-0192). Ausente = desligada: zero chamadas de rede. */
  autoUpdate?: boolean
}

/** As únicas preferências booleanas que o renderer pode alterar (`ragx:setPreference`). */
export const PREFERENCE_KEYS = ['tray', 'notifyStale', 'autoUpdate'] as const
export type PreferenceKey = (typeof PREFERENCE_KEYS)[number]

export interface PanelSettings extends RendererSettings {
  /**
   * Modo do Ollama que o usuário escolheu por último (gravado quando uma
   * troca de modo termina bem). Ausente: nunca escolheu. Só o processo
   * principal lê, para o catálogo decidir o `ollama-start`.
   */
  ollamaMode?: 'docker' | 'native'
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
    const parsed = JSON.parse(raw) as { onboardingDone?: unknown; ollamaMode?: unknown; pricing?: unknown } | null
    const settings: PanelSettings = { onboardingDone: parsed?.onboardingDone === true }
    const mode = parsed?.ollamaMode
    if (mode === 'docker' || mode === 'native') settings.ollamaMode = mode
    const pricing = parsePricing(parsed?.pricing)
    if (pricing !== null) settings.pricing = pricing
    // só `true` fica: ausente e qualquer outro valor são `false` (desligado por padrão)
    for (const key of PREFERENCE_KEYS) if ((parsed as Record<string, unknown> | null)?.[key] === true) settings[key] = true
    return settings
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

/** Lê, aplica `patch` e grava: um campo alterado nunca apaga os outros. */
export function updateSettings(dir: string, patch: Partial<PanelSettings>): PanelSettings {
  const next: PanelSettings = { ...readSettings(dir), ...patch }
  writeSettings(dir, next)
  return next
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

import type { Pricing } from './types/ragx-bridge'

/** Teto do preço aceito (o mesmo do processo principal, `electron/settings.ts`). */
export const MAX_PRICE = 10_000

export type Currency = Pricing['currency']

export const CURRENCY_LABEL: Record<Currency, string> = { BRL: 'Real (R$)', USD: 'Dólar (US$)', EUR: 'Euro (€)' }

/**
 * Quanto os tokens economizados valem a `perMTok` por milhão de tokens de entrada (RAGX-0186). Nunca negativo: se o
 * RAGX entregou mais do que o limite estimado, a economia é 0, não um valor negativo. O preço é da pessoa: o RAGX não
 * embute tabela de preços nem busca câmbio.
 */
export function savedMoney(savedTokens: number, perMTok: number): number {
  return (Math.max(0, savedTokens) / 1_000_000) * perMTok
}

/** "R$ 6,00"; entre 0 e 0,005 diz "menos de R$ 0,01" (na moeda escolhida), em vez de arredondar para "R$ 0,00". */
export function formatMoney(value: number, currency: Currency): string {
  const fmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency })
  if (value > 0 && value < 0.005) return `menos de ${fmt.format(0.01)}`
  return fmt.format(value)
}

/** Lê o preço digitado ("3,5" ou "3.5"); `null` quando não é número entre 0 (exclusivo) e `MAX_PRICE`. */
export function parsePriceInput(text: string): number | null {
  const n = Number(text.trim().replace(',', '.'))
  return Number.isFinite(n) && n > 0 && n <= MAX_PRICE ? n : null
}

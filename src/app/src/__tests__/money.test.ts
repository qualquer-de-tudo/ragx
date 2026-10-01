import { describe, expect, it } from 'vitest'
import { formatMoney, parsePriceInput, savedMoney } from '../money'

describe('money', () => {
  it('2 milhões de tokens a 3 por milhão valem 6; nunca negativo', () => {
    expect(savedMoney(2_000_000, 3)).toBe(6)
    expect(savedMoney(-500, 3)).toBe(0)
    expect(savedMoney(0, 3)).toBe(0)
  })

  it('formata na moeda em pt-BR', () => {
    expect(formatMoney(6, 'BRL').replace(/\s/g, ' ')).toBe('R$ 6,00')
    expect(formatMoney(1234.5, 'USD').replace(/\s/g, ' ')).toBe('US$ 1.234,50')
    expect(formatMoney(2, 'EUR')).toContain('€')
  })

  it('entre 0 e 0,005 diz "menos de" na moeda escolhida; 0 fica 0', () => {
    expect(formatMoney(0.001, 'BRL').replace(/\s/g, ' ')).toBe('menos de R$ 0,01')
    expect(formatMoney(0.001, 'USD')).toContain('menos de US$')
    expect(formatMoney(0, 'BRL').replace(/\s/g, ' ')).toBe('R$ 0,00')
    expect(formatMoney(0.005, 'BRL').replace(/\s/g, ' ')).toBe('R$ 0,01')
  })

  it('lê o preço digitado com vírgula ou ponto e recusa o resto', () => {
    expect(parsePriceInput('3,5')).toBe(3.5)
    expect(parsePriceInput(' 15 ')).toBe(15)
    for (const bad of ['', 'abc', '0', '-2', '10001', 'NaN', 'Infinity']) expect(parsePriceInput(bad)).toBeNull()
  })
})

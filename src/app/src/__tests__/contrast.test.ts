/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { mix, parseColor, ratio, type Rgba } from '../test/wcag'

const CSS = path.resolve(__dirname, '..', 'index.css')

/** Variáveis do bloco de tema (`:root` hoje; a RAGX-0193 acrescenta o claro com o seletor dele). */
function tokens(selector: string): Record<string, string> {
  const css = fs.readFileSync(CSS, 'utf-8')
  const start = css.indexOf(`${selector} {`)
  if (start < 0) throw new Error(`bloco ${selector} não encontrado em index.css`)
  const body = css.slice(start, css.indexOf('}', start))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}

const THEMES: Record<string, string> = { escuro: ':root', claro: ":root[data-theme='light']" }

const SURFACES = ['--bg', '--surface', '--surface-2', '--surface-3'] as const

describe('sanidade do helper', () => {
  it('preto sobre branco é 21:1 e igual sobre igual é 1:1', () => {
    expect(ratio(parseColor('#000'), parseColor('#ffffff'))).toBeCloseTo(21, 5)
    expect(ratio(parseColor('#123456'), parseColor('#123456'))).toBeCloseTo(1, 5)
  })
  it('lê rgba e mistura como color-mix', () => {
    expect(parseColor('rgba(59, 130, 246, 0.14)')).toEqual({ r: 59, g: 130, b: 246, a: 0.14 })
    const m = mix(parseColor('#ffffff'), parseColor('#000000'), 50)
    expect(Math.round(m.r)).toBe(128)
  })
})

describe.each(Object.entries(THEMES))('contraste AA, tema %s', (_name, selector) => {
  const t = tokens(selector)
  const c = (name: string): Rgba => {
    if (!(name in t)) throw new Error(`token ${name} ausente`)
    return parseColor(t[name])
  }
  const AA = 4.5

  it.each(['--ink', '--ink-2', '--ink-3'])('%s sobre as quatro superfícies >= 4,5:1', (ink) => {
    for (const s of SURFACES) expect(ratio(c(ink), c(s)), `${ink} em ${s}`).toBeGreaterThanOrEqual(AA)
  })

  it.each(['--good', '--warning', '--accent-text', '--critical-text'])('%s: puro e no selo (10%) sobre as quatro superfícies >= 4,5:1', (tone) => {
    for (const s of SURFACES) {
      expect(ratio(c(tone), c(s)), `${tone} puro em ${s}`).toBeGreaterThanOrEqual(AA)
      const wash = mix(c(tone), c(s), 10)
      expect(ratio(c(tone), wash), `${tone} no selo sobre ${s}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('texto branco sobre o preenchimento do botão primário e do perigo >= 4,5:1', () => {
    expect(ratio(c('--accent-ink'), c('--accent-solid')), 'accent-ink em accent-solid').toBeGreaterThanOrEqual(AA)
    expect(ratio(c('--accent-ink'), c('--critical-solid')), 'accent-ink em critical-solid').toBeGreaterThanOrEqual(AA)
  })

  it('o hover dos botões (94% do preenchimento + 6% de branco) segue >= 4,5:1 com texto branco', () => {
    const white = parseColor('#ffffff')
    for (const solid of ['--accent-solid', '--critical-solid']) {
      expect(ratio(c('--accent-ink'), mix(c(solid), white, 94)), `${solid} no hover`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('borda de controle e séries do gráfico >= 3:1 sobre a superfície (WCAG 1.4.11)', () => {
    for (const tok of ['--line-control', '--series-delivered', '--series-baseline']) {
      expect(ratio(c(tok), c('--surface')), `${tok} em surface`).toBeGreaterThanOrEqual(3)
    }
  })
})

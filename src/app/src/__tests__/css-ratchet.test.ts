/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// Catraca de espaçamento (RAGX-0178): `gap`, `padding` e `margin` com `px` literal só podem diminuir. Um valor da
// escala (`--sp-*`) não conta. Ao migrar mais declarações para os tokens, baixe o número em `css-ratchet.json`.
const CSS = path.resolve(__dirname, '..', 'App.css')
const LIMIT = path.resolve(__dirname, 'css-ratchet.json')

const DECL = /^\s*(gap|row-gap|column-gap|padding[a-z-]*|margin[a-z-]*):/
const PX = /\d(?:\.\d+)?px/

function literalSpacing(): number {
  return fs
    .readFileSync(CSS, 'utf-8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((l) => DECL.test(l) && PX.test(l)).length
}

describe('catraca de espaçamento em App.css', () => {
  const { spacingPxDeclarations } = JSON.parse(fs.readFileSync(LIMIT, 'utf-8')) as { spacingPxDeclarations: number }

  it('não passa do limite registrado', () => {
    expect(literalSpacing()).toBeLessThanOrEqual(spacingPxDeclarations)
  })

  it('o limite registrado não está folgado: baixe-o junto com a migração', () => {
    expect(literalSpacing()).toBe(spacingPxDeclarations)
  })
})

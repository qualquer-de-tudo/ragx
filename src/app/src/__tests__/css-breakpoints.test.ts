/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { BREAKPOINTS } from '../breakpoints'

// RAGX-0181: só 640, 900 e 1200 em `@media (max-width)` / `(min-width)`.
const SRC = path.resolve(__dirname, '..')

function widthsIn(file: string): number[] {
  const css = fs.readFileSync(path.join(SRC, file), 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')
  return [...css.matchAll(/@media[^{]*\((?:max|min)-width:\s*(\d+)px\)/g)].map((m) => Number(m[1]))
}

describe('breakpoints do CSS', () => {
  it.each(['App.css', 'index.css'])('%s só usa os breakpoints do projeto', (file) => {
    for (const w of widthsIn(file)) expect(BREAKPOINTS as readonly number[], `${file}: ${w}px`).toContain(w)
  })

  it('a varredura enxerga as consultas (não está vazia)', () => {
    expect(widthsIn('App.css').length + widthsIn('index.css').length).toBeGreaterThan(3)
  })
})

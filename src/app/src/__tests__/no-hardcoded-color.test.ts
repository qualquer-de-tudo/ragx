/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// Toda cor do renderer vem de um token (RAGX-0178): hex, rgb() e rgba() só dentro dos blocos `:root` (e, para a
// RAGX-0193, dos blocos de tema). Em `.tsx`, nenhuma cor literal.
const ROOT = path.resolve(__dirname, '..') // src/app/src

function files(dir: string, pattern: RegExp): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' || e.name === 'test' ? [] : files(full, pattern)
    return pattern.test(e.name) ? [full] : []
  })
}

/** Troca por linhas vazias os comentários e os blocos de tema, mantendo a numeração de linhas. */
function withoutThemeBlocks(src: string): string {
  const blank = (m: string) => m.replace(/[^\n]/g, '')
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|\n)(:root(?:\[[^\]]*\])?)\s*\{[^}]*\}/g, blank)
}

const COLOR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(/

describe('nenhuma cor literal fora dos tokens', () => {
  it.each(files(ROOT, /\.(css|tsx)$/))('%s', (file) => {
    const found = withoutThemeBlocks(fs.readFileSync(file, 'utf-8'))
      .split('\n')
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => COLOR.test(line))
      .map(({ line, n }) => `${path.relative(ROOT, file)}:${n}: ${line.trim()}`)
    expect(found).toEqual([])
  })
})

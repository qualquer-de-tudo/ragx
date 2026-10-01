/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// RAGX-0179: o padrão mora num primitivo. `role="radio"`, `role="switch"` e `<svg` só aparecem em `components/ui/`
// (mais a marca da logo e os gráficos de economia e de duração das indexações, que são desenho próprio, não ícone).
const ROOT = path.resolve(__dirname, '..') // src/app/src
const ALLOWED = ['components/ui/', 'components/brand/RagxMark.tsx', 'components/project/TokenSavings.tsx', 'components/project/IndexHealth.tsx']

function files(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' || e.name === 'test' ? [] : files(full)
    return e.name.endsWith('.tsx') ? [full] : []
  })
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:\\])\/\/.*$/gm, '$1')
}

const PATTERN = /role=["']radio["']|role=["']switch["']|<svg\b/

describe('padrões de UI só nos primitivos', () => {
  const outside = files(ROOT).filter((f) => !ALLOWED.some((a) => path.relative(ROOT, f).replaceAll('\\', '/').startsWith(a)))

  it.each(outside)('%s', (file) => {
    const found = stripComments(fs.readFileSync(file, 'utf-8'))
      .split('\n')
      .filter((l) => PATTERN.test(l))
    expect(found).toEqual([])
  })

  it('a varredura enxerga os primitivos (não está vazia)', () => {
    const ui = files(path.join(ROOT, 'components', 'ui'))
      .map((f) => fs.readFileSync(f, 'utf-8'))
      .join('\n')
    expect(ui).toMatch(/role="radio"/)
    expect(ui).toMatch(/role="switch"/)
    expect(ui).toMatch(/<svg/)
  })
})

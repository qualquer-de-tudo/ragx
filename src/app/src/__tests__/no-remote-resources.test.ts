/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// O painel não carrega nada de fora (RAGX-0194): é isso que deixa a CSP de produção restritiva.
const ROOT = path.resolve(__dirname, '..') // src/app/src
const HTML = path.resolve(__dirname, '..', '..', 'index.html')

function files(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' || e.name === 'test' ? [] : files(full)
    return /\.(tsx?|css|html)$/.test(e.name) ? [full] : []
  })
}

// Mesmo recorte de `no-em-dash.test.ts`: tira comentários antes de procurar.
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(^|[^:\\])\/\/.*$/gm, '$1')
}

const REMOTE = /https?:\/\/|wss?:\/\/|@import|url\(\s*['"]?https?:/

describe('nenhum recurso remoto no renderer', () => {
  it.each([...files(ROOT), HTML])('%s', (file) => {
    const offending = stripComments(fs.readFileSync(file, 'utf-8'))
      .split('\n')
      .filter((line) => REMOTE.test(line))
    expect(offending).toEqual([])
  })
})

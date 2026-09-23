/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(__dirname, '..') // src/app/src
const ELECTRON = path.resolve(__dirname, '..', '..', 'electron') // src/app/electron
const HTML = path.resolve(__dirname, '..', '..', 'index.html')

function files(dir: string, pattern: RegExp): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' || e.name === 'test' ? [] : files(full, pattern)
    return pattern.test(e.name) ? [full] : []
  })
}

// Remove comentários de linha e de bloco (TS/CSS) e comentários HTML antes de
// procurar. (Um "/* */" literal aqui dentro de um comentário de bloco fecharia
// o próprio comentário, por isso a descrição fica em comentário de linha.)
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(^|[^:\\])\/\/.*$/gm, '$1')
}

function offendingLines(file: string): string[] {
  return stripComments(fs.readFileSync(file, 'utf-8'))
    .split('\n')
    .filter((line) => line.includes('—'))
}

describe('texto visível sem travessão', () => {
  it.each([...files(ROOT, /\.(tsx?|css|html)$/), HTML])('%s', (file) => {
    expect(offendingLines(file)).toEqual([])
  })
})

// O processo principal também produz texto que chega à tela: erros de
// tarefa, notas, resumos das checagens de conexão, mensagens de recusa.
describe('texto do processo principal sem travessão', () => {
  it.each(files(ELECTRON, /\.ts$/))('%s', (file) => {
    expect(offendingLines(file)).toEqual([])
  })
})

import { describe, expect, it, vi, afterEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { readSettings, updateSettings, writeSettings } from '../settings'

function mkTmp(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-settings-test-'))
}

describe('readSettings', () => {
  it('devolve onboardingDone:false quando a pasta nao existe', () => {
    expect(readSettings(path.join(os.tmpdir(), 'nao-existe-de-verdade'))).toEqual({ onboardingDone: false })
  })

  it('devolve onboardingDone:false quando o arquivo esta corrompido', () => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), 'isso nao e json')
    expect(readSettings(dir)).toEqual({ onboardingDone: false })
  })

  it('le o que writeSettings gravou', () => {
    const dir = mkTmp()
    writeSettings(dir, { onboardingDone: true })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true })
  })

  it('le e preserva o modo preferido do Ollama (docker ou native)', () => {
    const dir = mkTmp()
    writeSettings(dir, { onboardingDone: true, ollamaMode: 'native' })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, ollamaMode: 'native' })
    writeSettings(dir, { onboardingDone: false, ollamaMode: 'docker' })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: false, ollamaMode: 'docker' })
  })

  it('modo invalido no arquivo vira ausente', () => {
    const dir = mkTmp()
    for (const bad of ['gpu', 'none', 'conflict', 42, null, ['docker']]) {
      fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, ollamaMode: bad }))
      expect(readSettings(dir)).toStrictEqual({ onboardingDone: true })
    }
  })
})

describe('updateSettings', () => {
  it('altera so o que foi pedido e preserva o resto', () => {
    const dir = mkTmp()
    writeSettings(dir, { onboardingDone: true, ollamaMode: 'docker' })
    updateSettings(dir, { ollamaMode: 'native' })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, ollamaMode: 'native' })
    updateSettings(dir, { onboardingDone: false })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: false, ollamaMode: 'native' })
  })

  it('funciona sem arquivo anterior', () => {
    const dir = mkTmp()
    updateSettings(dir, { ollamaMode: 'docker' })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: false, ollamaMode: 'docker' })
  })
})

describe('writeSettings', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('grava de forma atomica (nenhum .tmp sobra depois de uma escrita normal)', () => {
    const dir = mkTmp()
    writeSettings(dir, { onboardingDone: true })
    const leftover = fs.readdirSync(dir).filter((f) => f.endsWith('.tmp'))
    expect(leftover).toEqual([])
  })

  it('remove o .tmp e propaga o erro quando renameSync falha (fix round 1)', () => {
    const dir = mkTmp()
    const renameSpy = vi.spyOn(fs, 'renameSync').mockImplementation(() => {
      throw new Error('rename falhou')
    })

    expect(() => writeSettings(dir, { onboardingDone: true })).toThrow('rename falhou')
    renameSpy.mockRestore()

    const leftover = fs.readdirSync(dir).filter((f) => f.endsWith('.tmp'))
    expect(leftover).toEqual([])
  })
})

describe('pricing (RAGX-0186)', () => {
  it('arquivo antigo, sem o campo, abre igual a antes', () => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true })
  })

  it('pricing válido sobrevive a reabrir e não apaga os outros campos', () => {
    const dir = mkTmp()
    writeSettings(dir, { onboardingDone: true, ollamaMode: 'native' })
    updateSettings(dir, { pricing: { currency: 'BRL', perMTokInput: 15 } })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, ollamaMode: 'native', pricing: { currency: 'BRL', perMTokInput: 15 } })
  })

  it.each([
    ['moeda fora do conjunto', { currency: 'XYZ', perMTokInput: 3 }],
    ['preço zero', { currency: 'USD', perMTokInput: 0 }],
    ['preço negativo', { currency: 'USD', perMTokInput: -1 }],
    ['preço acima do teto', { currency: 'USD', perMTokInput: 10001 }],
    ['preço em texto', { currency: 'USD', perMTokInput: '3' }],
    ['não é objeto', 'BRL'],
  ])('%s vira ausente', (_n, pricing) => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, pricing }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true })
  })
})

describe('tray e notifyStale (RAGX-0191)', () => {
  it('padrão desligado: ausentes, e readSettings sem os campos não os inventa', () => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true }))
    const s = readSettings(dir)
    expect(s.tray).toBeUndefined()
    expect(s.notifyStale).toBeUndefined()
  })

  it('valor inválido vira desligado; true sobrevive; os outros campos não somem', () => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, ollamaMode: 'docker', tray: 'sim', notifyStale: true }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, ollamaMode: 'docker', notifyStale: true })
    updateSettings(dir, { tray: true })
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, ollamaMode: 'docker', notifyStale: true, tray: true })
  })
})

describe('autoUpdate (RAGX-0192)', () => {
  it('ligada por padrão (ausente = ligada); valor inválido descartado; true e false explícitos sobrevivem', () => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true }))
    expect(readSettings(dir).autoUpdate).toBeUndefined()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, autoUpdate: 'sim' }))
    expect(readSettings(dir).autoUpdate).toBeUndefined()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, autoUpdate: true }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, autoUpdate: true })
    // desligar é uma escolha da pessoa: o `false` explícito fica gravado (apagar a chave ligaria de novo)
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, autoUpdate: false }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, autoUpdate: false })
  })
})

describe('theme (RAGX-0193)', () => {
  it('padrão escuro: o campo some; só light e system ficam; valor inválido volta ao padrão', () => {
    const dir = mkTmp()
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true })
    for (const bad of ['dark', 'roxo', 3, null]) {
      fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, theme: bad }))
      expect(readSettings(dir).theme).toBeUndefined()
    }
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ onboardingDone: true, ollamaMode: 'native', theme: 'light' }))
    expect(readSettings(dir)).toStrictEqual({ onboardingDone: true, ollamaMode: 'native', theme: 'light' })
  })
})

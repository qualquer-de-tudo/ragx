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

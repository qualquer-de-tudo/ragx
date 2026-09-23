import { describe, expect, it, vi, afterEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { readSettings, writeSettings } from '../settings'

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
    expect(readSettings(dir)).toEqual({ onboardingDone: true })
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

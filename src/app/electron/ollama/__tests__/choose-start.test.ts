import { describe, expect, it } from 'vitest'
import { chooseStartMode } from '../choose-start'
import type { OllamaEnvironment } from '../../../src/types/ragx-bridge'

function env(over: Partial<OllamaEnvironment> = {}): OllamaEnvironment {
  return {
    platform: 'win32',
    gpu: { vendor: 'none', name: null },
    docker: { installed: true, running: true },
    container: { exists: true, running: false },
    native: { installed: true, path: 'C:\\o\\ollama.exe', running: false },
    canInstallNative: true,
    apiUp: false,
    models: [],
    mode: 'none',
    recommendation: { mode: 'docker', reason: 'r' },
    ...over,
  }
}

const noContainer = { exists: false, running: false }
const noNative = { installed: false, path: null, running: false }

describe('chooseStartMode', () => {
  it('preferido disponível vence a recomendação', () => {
    expect(chooseStartMode(env({ recommendation: { mode: 'docker', reason: 'r' } }), 'native')).toBe('native')
    expect(chooseStartMode(env({ recommendation: { mode: 'native', reason: 'r' } }), 'docker')).toBe('docker')
  })

  it('preferido indisponível cai na recomendação disponível', () => {
    expect(chooseStartMode(env({ container: noContainer, recommendation: { mode: 'native', reason: 'r' } }), 'docker')).toBe(
      'native',
    )
    expect(chooseStartMode(env({ native: noNative, recommendation: { mode: 'docker', reason: 'r' } }), 'native')).toBe(
      'docker',
    )
  })

  it('sem preferido nem recomendação disponível: container, depois nativo', () => {
    expect(chooseStartMode(env({ native: noNative, recommendation: { mode: 'native', reason: 'r' } }), null)).toBe('docker')
    expect(chooseStartMode(env({ container: noContainer, recommendation: { mode: 'docker', reason: 'r' } }), null)).toBe(
      'native',
    )
  })

  it('nada instalado: null', () => {
    expect(chooseStartMode(env({ container: noContainer, native: noNative }), 'docker')).toBeNull()
    expect(chooseStartMode(env({ container: noContainer, native: noNative }), null)).toBeNull()
  })
})

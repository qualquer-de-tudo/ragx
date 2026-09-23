import { describe, expect, it, beforeEach } from 'vitest'
import path from 'node:path'
import { resolveOllama, resetOllamaCache } from '../paths'

describe('resolveOllama', () => {
  beforeEach(() => resetOllamaCache())

  it('acha no PATH', () => {
    const dir = path.join('C:', 'tools')
    const found = resolveOllama({
      env: { PATH: dir },
      platform: 'win32',
      exists: (p) => p === path.join(dir, 'ollama.exe'),
    })
    expect(found).toBe(path.join(dir, 'ollama.exe'))
  })

  it('cai para %LOCALAPPDATA%\\Programs\\Ollama quando o PATH do app não tem', () => {
    const local = path.join('C:', 'Users', 'fulano', 'AppData', 'Local')
    const expected = path.join(local, 'Programs', 'Ollama', 'ollama.exe')
    const found = resolveOllama({
      env: { PATH: '', LOCALAPPDATA: local },
      platform: 'win32',
      exists: (p) => p === expected,
    })
    expect(found).toBe(expected)
  })

  it('no Windows ignora .cmd', () => {
    const dir = path.join('C:', 'tools')
    const found = resolveOllama({
      env: { PATH: dir },
      platform: 'win32',
      exists: (p) => p === path.join(dir, 'ollama.cmd'),
    })
    expect(found).toBeNull()
  })

  it('remove aspas ao redor de segmentos do PATH', () => {
    const dir = path.join('C:', 'Program Files', 'Ollama')
    const expected = path.join(dir, 'ollama.exe')
    const found = resolveOllama({
      env: { PATH: `"${dir}"` },
      platform: 'win32',
      exists: (p) => p === expected,
    })
    expect(found).toBe(expected)
  })

  it('no Linux acha no PATH', () => {
    const expected = path.join('/usr/bin', 'ollama')
    const found = resolveOllama({ env: { PATH: '/usr/bin' }, platform: 'linux', exists: (p) => p === expected })
    expect(found).toBe(expected)
  })

  it('no macOS cai para /opt/homebrew/bin/ollama', () => {
    const expected = path.join('/opt/homebrew/bin', 'ollama')
    const found = resolveOllama({ env: { PATH: '/usr/bin' }, platform: 'darwin', exists: (p) => p === expected })
    expect(found).toBe(expected)
  })

  it('no posix cai para /usr/local/bin/ollama', () => {
    const expected = path.join('/usr/local/bin', 'ollama')
    const found = resolveOllama({ env: { PATH: '' }, platform: 'linux', exists: (p) => p === expected })
    expect(found).toBe(expected)
  })

  it('devolve null quando não acha', () => {
    expect(resolveOllama({ env: { PATH: '' }, platform: 'linux', exists: () => false })).toBeNull()
    expect(resolveOllama({ env: { PATH: '' }, platform: 'win32', exists: () => false })).toBeNull()
  })
})

import { describe, expect, it, beforeEach } from 'vitest'
import path from 'node:path'
import { resolveRagx, resetRagxCache, ragxCommand } from '../ragx-exe'

describe('resolveRagx', () => {
  beforeEach(() => resetRagxCache())

  it('acha no PATH', () => {
    const dir = path.join('C:', 'tools')
    const found = resolveRagx({
      env: { PATH: dir, PATHEXT: '.EXE;.CMD' },
      platform: 'win32',
      exists: (p) => p === path.join(dir, 'ragx.exe'),
    })
    expect(found).toBe(path.join(dir, 'ragx.exe'))
  })

  it('no Windows ignora .cmd (spawn sem shell não consegue lançar)', () => {
    const dir = path.join('C:', 'tools')
    const found = resolveRagx({
      env: { PATH: dir, PATHEXT: '.EXE;.CMD' },
      platform: 'win32',
      exists: (p) => p === path.join(dir, 'ragx.cmd'),
    })
    expect(found).toBeNull()
  })

  it('remove aspas ao redor de segmentos do PATH', () => {
    const dir = path.join('C:', 'Program Files', 'ragx')
    const expected = path.join(dir, 'ragx.exe')
    const found = resolveRagx({
      env: { PATH: `"${dir}"`, PATHEXT: '.EXE;.CMD' },
      platform: 'win32',
      exists: (p) => p === expected,
    })
    expect(found).toBe(expected)
  })

  it('cai para %USERPROFILE%\\.local\\bin quando o PATH do app não tem o ragx', () => {
    const home = path.join('C:', 'Users', 'fulano')
    const expected = path.join(home, '.local', 'bin', 'ragx.exe')
    const found = resolveRagx({
      env: { PATH: '', USERPROFILE: home },
      platform: 'win32',
      exists: (p) => p === expected,
    })
    expect(found).toBe(expected)
  })

  it('no posix procura ~/.local/bin/ragx', () => {
    const expected = path.join('/home/fulano', '.local', 'bin', 'ragx')
    const found = resolveRagx({
      env: { PATH: '/usr/bin', HOME: '/home/fulano' },
      platform: 'linux',
      exists: (p) => p === expected,
    })
    expect(found).toBe(expected)
  })

  it('devolve null quando não acha', () => {
    expect(resolveRagx({ env: { PATH: '' }, platform: 'linux', exists: () => false })).toBeNull()
  })
})

describe('ragxCommand', () => {
  beforeEach(() => resetRagxCache())

  it('não fixa a ausência em cache: acha o ragx instalado depois', () => {
    const achado = path.join('C:', 'u', '.local', 'bin', 'ragx.exe')
    let instalado = false
    const resolve = () => (instalado ? achado : null)
    expect(ragxCommand(resolve)).toBe('ragx')
    instalado = true
    expect(ragxCommand(resolve)).toBe(achado)
  })

  it('guarda em cache um caminho já achado', () => {
    const achado = path.join('C:', 'u', 'ragx.exe')
    let chamadas = 0
    const resolve = () => {
      chamadas += 1
      return achado
    }
    ragxCommand(resolve)
    ragxCommand(resolve)
    expect(chamadas).toBe(1)
  })
})

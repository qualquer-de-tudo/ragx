import { describe, expect, it, beforeEach } from 'vitest'
import path from 'node:path'
import { resolveRagx, resetRagxCache } from '../ragx-exe'

describe('resolveRagx', () => {
  beforeEach(() => resetRagxCache())

  it('acha no PATH', () => {
    const dir = path.join('C:', 'tools')
    const found = resolveRagx({
      env: { PATH: dir, PATHEXT: '.EXE;.CMD' },
      platform: 'win32',
      exists: (p) => p === path.join(dir, 'ragx.EXE'),
    })
    expect(found).toBe(path.join(dir, 'ragx.EXE'))
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

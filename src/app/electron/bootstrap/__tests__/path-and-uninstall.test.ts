import { describe, expect, it, vi } from 'vitest'
import path from 'node:path'
import { ensureUserPath, removeFromUserPath, type BootstrapState, type PathDeps } from '../path-user'
import { uninstallCli, type UninstallDeps } from '../uninstall'

const BIN = 'C:\\Users\\ana\\.local\\bin'

function fakePath(initial: string, state: BootstrapState = { pathAdded: false, binDir: null }) {
  const s = { path: initial, state }
  const deps: PathDeps = {
    getUserPath: async () => s.path,
    setUserPath: async (v) => {
      s.path = v
    },
    readState: () => s.state,
    writeState: (n) => {
      s.state = n
    },
  }
  return { s, deps }
}

describe('ensureUserPath', () => {
  it('adiciona e marca pathAdded', async () => {
    const { s, deps } = fakePath('C:\\a;C:\\b')
    expect(await ensureUserPath(BIN, deps)).toEqual({ added: true })
    expect(s.path).toBe(`C:\\a;C:\\b;${BIN}`)
    expect(s.state).toEqual({ pathAdded: true, binDir: BIN })
  })

  it('já presente (outra caixa, barra final): não muda nada e não marca pathAdded', async () => {
    const { s, deps } = fakePath(`C:\\a;${BIN.toUpperCase()}\\`)
    expect(await ensureUserPath(BIN, deps)).toEqual({ added: false })
    expect(s.path).toBe(`C:\\a;${BIN.toUpperCase()}\\`)
    expect(s.state.pathAdded).toBe(false)
  })

  it('rodar duas vezes não duplica e mantém o pathAdded da primeira', async () => {
    const { s, deps } = fakePath('')
    await ensureUserPath(BIN, deps)
    await ensureUserPath(BIN, deps)
    expect(s.path).toBe(BIN)
    expect(s.state.pathAdded).toBe(true)
  })
})

describe('removeFromUserPath', () => {
  it('remove só quando o app foi quem adicionou', async () => {
    const { s, deps } = fakePath(`C:\\a;${BIN};C:\\b`, { pathAdded: true, binDir: BIN })
    expect(await removeFromUserPath(deps)).toEqual({ removed: true })
    expect(s.path).toBe('C:\\a;C:\\b')
    expect(s.state).toEqual({ pathAdded: false, binDir: null })
  })

  it('pasta que já estava lá (pathAdded false) fica como está', async () => {
    const { s, deps } = fakePath(`C:\\a;${BIN}`)
    expect(await removeFromUserPath(deps)).toEqual({ removed: false })
    expect(s.path).toBe(`C:\\a;${BIN}`)
  })
})

function uninstallDeps(over: Partial<UninstallDeps> = {}) {
  const calls: string[] = []
  const deps: UninstallDeps = {
    exec: async (file, args) => {
      calls.push(`${path.basename(file)} ${args.join(' ')}`)
      return { code: 0, stdout: '', stderr: '' }
    },
    ragxPath: () => 'C:\\bin\\ragx.exe',
    uvPath: () => 'C:\\app\\uv.exe',
    removeFromPath: async () => {
      calls.push('path')
      return { removed: true }
    },
    rm: vi.fn(async (p: string) => {
      calls.push(`rm ${p}`)
    }),
    homedir: 'C:\\Users\\ana',
    ...over,
  }
  return { deps, calls }
}

describe('uninstallCli', () => {
  it('ordem: MCP, ferramenta, PATH; sem removeData não apaga o hub', async () => {
    const { deps, calls } = uninstallDeps()
    const r = await uninstallCli({ removeData: false }, deps)
    expect(calls).toEqual(['ragx.exe mcp uninstall', 'uv.exe tool uninstall ragx', 'path'])
    expect(r.errors).toEqual([])
  })

  it('removeData apaga exatamente ~/.ragx', async () => {
    const { deps, calls } = uninstallDeps()
    await uninstallCli({ removeData: true }, deps)
    expect(calls).toContain(`rm ${path.join('C:\\Users\\ana', '.ragx')}`)
  })

  it('ragx.exe travado: o erro é reportado e PATH/hub ainda são tratados', async () => {
    const { deps, calls } = uninstallDeps({
      exec: async (file, args) => {
        if (args[0] === 'tool') return { code: 2, stdout: '', stderr: 'Acesso negado. (os error 5)' }
        return { code: 0, stdout: '', stderr: '' }
      },
    })
    const r = await uninstallCli({ removeData: true }, deps)
    expect(r.errors[0]).toMatch(/feche o Claude Code/)
    expect(calls).toContain('path')
    expect(calls.some((c) => c.startsWith('rm '))).toBe(true)
  })

  it('sem ragx instalado pula o MCP sem erro', async () => {
    const { deps, calls } = uninstallDeps({ ragxPath: () => null })
    const r = await uninstallCli({ removeData: false }, deps)
    expect(calls[0]).toBe('uv.exe tool uninstall ragx')
    expect(r.errors).toEqual([])
  })

  it('uv dizendo que o ragx não está instalado não é erro', async () => {
    const { deps } = uninstallDeps({
      exec: async () => ({ code: 2, stdout: '', stderr: 'error: `ragx` is not installed' }),
    })
    const r = await uninstallCli({ removeData: false }, deps)
    expect(r.errors.filter((e) => e.includes('uv tool'))).toEqual([])
  })

  it('homedir vazio ou relativo: não apaga nada e avisa', async () => {
    for (const homedir of ['', 'relativo']) {
      const { deps } = uninstallDeps({ homedir })
      const r = await uninstallCli({ removeData: true }, deps)
      expect(deps.rm).not.toHaveBeenCalled()
      expect(r.errors.some((e) => e.includes('hub'))).toBe(true)
    }
  })
})

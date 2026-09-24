import { describe, expect, it, vi } from 'vitest'
import { afterRagxInstall } from '../post-install'
import type { BootstrapState, PathDeps } from '../path-user'

function pathDeps(initial: string) {
  const s = { path: initial, state: { pathAdded: false, binDir: null } as BootstrapState }
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

describe('afterRagxInstall', () => {
  it('esquece o cache, acha o ragx e põe a pasta dele no PATH', async () => {
    const { s, deps } = pathDeps('C:\\a')
    const resetCache = vi.fn()
    const r = await afterRagxInstall({
      resetCache,
      resolveRagx: () => 'C:\\Users\\ana\\.local\\bin\\ragx.exe',
      pathDeps: deps,
    })
    expect(resetCache).toHaveBeenCalledOnce()
    expect(r).toEqual({ found: true, pathAdded: true })
    expect(s.path).toBe('C:\\a;C:\\Users\\ana\\.local\\bin')
  })

  it('ragx.exe não apareceu: found false e o PATH fica como está', async () => {
    const { s, deps } = pathDeps('C:\\a')
    const r = await afterRagxInstall({ resetCache: () => {}, resolveRagx: () => null, pathDeps: deps })
    expect(r).toEqual({ found: false, pathAdded: false })
    expect(s.path).toBe('C:\\a')
  })

  it('pasta já no PATH (uv/claude): não marca pathAdded', async () => {
    const { s, deps } = pathDeps('C:\\Users\\ana\\.local\\bin')
    const r = await afterRagxInstall({
      resetCache: () => {},
      resolveRagx: () => 'C:\\Users\\ana\\.local\\bin\\ragx.exe',
      pathDeps: deps,
    })
    expect(r).toEqual({ found: true, pathAdded: false })
    expect(s.state.pathAdded).toBe(false)
  })
})

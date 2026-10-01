import { beforeEach, describe, expect, it, vi } from 'vitest'
import { checkRagx, resetRagxVersionCache, type CheckDeps } from '../checks'
import type { ExecResult } from '../../system/exec'

const EXE = 'C:\\Users\\x\\.local\\bin\\ragx.exe'

function deps(over: Partial<CheckDeps> & { exec: CheckDeps['exec'] }): CheckDeps {
  return {
    resolveRagx: () => EXE,
    readFile: () => null,
    exists: () => true,
    httpGetJson: async () => null,
    homeDir: 'C:\\Users\\x',
    ...over,
  }
}

const ok = (stdout: string): ExecResult => ({ code: 0, stdout, stderr: '' })

beforeEach(() => resetRagxVersionCache())

describe('checkRagx - versão em cache por assinatura do executável (RAGX-0173)', () => {
  it('`ragx --version` roda UMA vez enquanto o mtime e o tamanho do executável não mudam', async () => {
    const exec = vi.fn(async () => ok('ragx 1.0.0\n'))
    const d = deps({ exec, stat: () => ({ mtimeMs: 100, size: 5000 }) })
    const a = await checkRagx(d)
    const b = await checkRagx(d)
    const c = await checkRagx(d)
    expect(exec).toHaveBeenCalledTimes(1)
    expect(a.state).toBe('ok')
    expect(c.facts).toEqual(a.facts)
    expect(b.facts).toContainEqual({ label: 'Versão', value: 'ragx 1.0.0' })
  })

  it('roda de novo quando o mtime, o tamanho ou o caminho mudam', async () => {
    const exec = vi.fn(async () => ok('ragx 1.0.0\n'))
    let sig = { mtimeMs: 100, size: 5000 }
    let path = EXE
    const d = deps({ exec, stat: () => sig, resolveRagx: () => path })
    await checkRagx(d)
    sig = { mtimeMs: 200, size: 5000 } // atualizaram o executável
    await checkRagx(d)
    sig = { mtimeMs: 200, size: 5100 }
    await checkRagx(d)
    path = 'C:\\outro\\ragx.exe'
    await checkRagx(d)
    expect(exec).toHaveBeenCalledTimes(4)
  })

  it('resetRagxVersionCache (uma tarefa ragx-install terminou) força a consulta', async () => {
    const exec = vi.fn(async () => ok('ragx 1.0.0\n'))
    const d = deps({ exec, stat: () => ({ mtimeMs: 1, size: 1 }) })
    await checkRagx(d)
    resetRagxVersionCache()
    await checkRagx(d)
    expect(exec).toHaveBeenCalledTimes(2)
  })

  it('só resposta com código 0 entra no cache: uma falha passageira não fica', async () => {
    let n = 0
    const exec = vi.fn(async (): Promise<ExecResult> => (++n === 1 ? { code: 1, stdout: '', stderr: 'boom' } : ok('ragx 1.0.0\n')))
    const d = deps({ exec, stat: () => ({ mtimeMs: 1, size: 1 }) })
    expect((await checkRagx(d)).state).toBe('error')
    expect((await checkRagx(d)).state).toBe('ok')
    await checkRagx(d)
    expect(exec).toHaveBeenCalledTimes(2) // a falha não foi guardada; o sucesso, sim
  })

  it('sem `stat` (ou com o arquivo ilegível) não há cache: roda a cada checagem, como antes', async () => {
    const exec = vi.fn(async () => ok('ragx 1.0.0\n'))
    await checkRagx(deps({ exec }))
    await checkRagx(deps({ exec }))
    await checkRagx(deps({ exec, stat: () => null }))
    expect(exec).toHaveBeenCalledTimes(3)
  })
})

import { describe, expect, it } from 'vitest'
import { isInsideGitWorkTree, readGitHead } from '../git'
import type { ExecFn } from '../../system/exec'

function fake(map: Record<string, { code: number; stdout: string }>): ExecFn {
  return async (_file, args) => {
    const r = map[args.join(' ')] ?? { code: 128, stdout: '' }
    return { ...r, stderr: '' }
  }
}

describe('readGitHead', () => {
  it('lê branch e commit', async () => {
    const exec = fake({
      '--no-optional-locks rev-parse HEAD': { code: 0, stdout: 'abc123\n' },
      '--no-optional-locks symbolic-ref --quiet --short HEAD': { code: 0, stdout: 'feat/x\n' },
    })
    expect(await readGitHead('C:/p', exec)).toEqual({ branch: 'feat/x', commit: 'abc123' })
  })

  it('HEAD destacado tem branch null', async () => {
    const exec = fake({ '--no-optional-locks rev-parse HEAD': { code: 0, stdout: 'abc123\n' } })
    expect(await readGitHead('C:/p', exec)).toEqual({ branch: null, commit: 'abc123' })
  })

  it('fora de repo devolve null', async () => {
    expect(await readGitHead('C:/p', fake({}))).toBeNull()
  })
})

describe('isInsideGitWorkTree', () => {
  it('true quando git responde "true" na pasta', async () => {
    const calls: Array<{ args: string[]; cwd?: string }> = []
    const exec: ExecFn = async (_file, args, opts) => {
      calls.push({ args, cwd: opts?.cwd })
      return { code: 0, stdout: 'true\n', stderr: '' }
    }
    expect(await isInsideGitWorkTree('C:/p', exec)).toBe(true)
    expect(calls).toEqual([{ args: ['--no-optional-locks', 'rev-parse', '--is-inside-work-tree'], cwd: 'C:/p' }])
  })

  it('false fora de repo (código != 0) ou dentro do .git ("false")', async () => {
    expect(await isInsideGitWorkTree('C:/p', fake({}))).toBe(false)
    const insideDotGit: ExecFn = async () => ({ code: 0, stdout: 'false\n', stderr: '' })
    expect(await isInsideGitWorkTree('C:/p/.git', insideDotGit)).toBe(false)
  })
})

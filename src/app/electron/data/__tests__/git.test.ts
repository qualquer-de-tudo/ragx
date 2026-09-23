import { describe, expect, it } from 'vitest'
import { readGitHead } from '../git'
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

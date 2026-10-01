import { execFileSync, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { readGitHeadFromFiles, resetGitCache } from '../git-files'
import { readGitHead } from '../git'
import type { ExecFn } from '../../system/exec'

const hasGit = spawnSync('git', ['--version']).status === 0
let base: string

const git = (cwd: string, ...args: string[]): string =>
  execFileSync('git', ['-c', 'user.email=t@t', '-c', 'user.name=t', '-c', 'init.defaultBranch=main', ...args], {
    cwd,
    encoding: 'utf-8',
  }).trim()

/** O que o `git` real responde (a referência que a leitura por arquivos precisa igualar). */
function real(cwd: string): { branch: string | null; commit: string } | null {
  const head = spawnSync('git', ['rev-parse', 'HEAD'], { cwd, encoding: 'utf-8' })
  if (head.status !== 0) return null
  const ref = spawnSync('git', ['symbolic-ref', '--quiet', '--short', 'HEAD'], { cwd, encoding: 'utf-8' })
  return { branch: ref.status === 0 ? ref.stdout.trim() : null, commit: head.stdout.trim() }
}

beforeAll(() => {
  base = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-gitreal-'))
  resetGitCache()
})
afterAll(() => fs.rmSync(base, { recursive: true, force: true }))

function repo(name: string): string {
  const dir = path.join(base, name)
  fs.mkdirSync(dir, { recursive: true })
  git(dir, 'init', '-q')
  return dir
}

function commit(dir: string, text: string): void {
  fs.writeFileSync(path.join(dir, 'f.txt'), text)
  git(dir, 'add', '.')
  git(dir, 'commit', '-q', '-m', text)
}

describe.skipIf(!hasGit)('readGitHeadFromFiles contra o git real', () => {
  it('branch comum', () => {
    const dir = repo('comum')
    commit(dir, 'um')
    expect(readGitHeadFromFiles(dir)).toEqual(real(dir))
  })

  it('branch com barra no nome', () => {
    const dir = repo('barra')
    commit(dir, 'um')
    git(dir, 'checkout', '-q', '-b', 'feat/x')
    commit(dir, 'dois')
    expect(readGitHeadFromFiles(dir)).toEqual(real(dir))
    expect(readGitHeadFromFiles(dir)).toMatchObject({ branch: 'feat/x' })
  })

  it('ref empacotada (git pack-refs --all)', () => {
    const dir = repo('empacotada')
    commit(dir, 'um')
    git(dir, 'pack-refs', '--all')
    expect(fs.existsSync(path.join(dir, '.git', 'packed-refs'))).toBe(true)
    expect(readGitHeadFromFiles(dir)).toEqual(real(dir))
  })

  it('HEAD destacado', () => {
    const dir = repo('destacado')
    commit(dir, 'um')
    commit(dir, 'dois')
    git(dir, 'checkout', '-q', '--detach', 'HEAD~1')
    expect(readGitHeadFromFiles(dir)).toEqual(real(dir))
    expect(readGitHeadFromFiles(dir)).toMatchObject({ branch: null })
  })

  it('worktree', () => {
    const dir = repo('principal')
    commit(dir, 'um')
    git(dir, 'branch', 'outro')
    const wt = path.join(base, 'wt-outro')
    git(dir, 'worktree', 'add', '-q', wt, 'outro')
    expect(readGitHeadFromFiles(wt)).toEqual(real(wt))
    expect(readGitHeadFromFiles(wt)).toMatchObject({ branch: 'outro' })
  })

  it('repositório sem commit', () => {
    const dir = repo('vazio')
    expect(real(dir)).toBeNull()
    expect(readGitHeadFromFiles(dir)).toBeNull()
  })

  it('subpasta do repositório', () => {
    const dir = repo('sub')
    commit(dir, 'um')
    const sub = path.join(dir, 'a', 'b')
    fs.mkdirSync(sub, { recursive: true })
    expect(readGitHeadFromFiles(sub)).toEqual(real(sub))
  })
})

describe.skipIf(!hasGit)('readGitHead: o git só roda como último recurso', () => {
  it('repositório normal: nenhum processo', async () => {
    const dir = repo('sem-processo')
    commit(dir, 'um')
    let chamadas = 0
    const exec: ExecFn = async () => {
      chamadas += 1
      return { code: 0, stdout: '', stderr: '' }
    }
    const r = await readGitHead(dir, exec)
    expect(r).toEqual(real(dir))
    expect(chamadas).toBe(0)
  })

  it('reftable continua mostrando branch e commit, via git', async () => {
    const dir = repo('reftable')
    commit(dir, 'um')
    fs.appendFileSync(path.join(dir, '.git', 'config'), '\n[extensions]\n\trefStorage = reftable\n')
    const chamadas: string[][] = []
    const exec: ExecFn = async (_f, args) => {
      chamadas.push(args)
      return args.includes('rev-parse')
        ? { code: 0, stdout: 'abc123\n', stderr: '' }
        : { code: 0, stdout: 'main\n', stderr: '' }
    }
    expect(await readGitHead(dir, exec)).toEqual({ branch: 'main', commit: 'abc123' })
    expect(chamadas).toHaveLength(2)
  })
})

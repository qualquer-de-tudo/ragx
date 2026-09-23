import { execFileText, type ExecFn } from '../system/exec'

export interface GitHead {
  branch: string | null
  commit: string
}

/** `--no-optional-locks`: o painel consulta a cada ciclo e não pode disputar o .git/index com o usuário. */
export async function readGitHead(projectPath: string, exec: ExecFn = execFileText): Promise<GitHead | null> {
  const head = await exec('git', ['--no-optional-locks', 'rev-parse', 'HEAD'], { cwd: projectPath })
  if (head.code !== 0 || !head.stdout.trim()) return null
  const ref = await exec('git', ['--no-optional-locks', 'symbolic-ref', '--quiet', '--short', 'HEAD'], {
    cwd: projectPath,
  })
  return { branch: ref.code === 0 && ref.stdout.trim() ? ref.stdout.trim() : null, commit: head.stdout.trim() }
}

/** A pasta está dentro de uma árvore de trabalho git? Fora de repo (ou git ausente), `false`. */
export async function isInsideGitWorkTree(folder: string, exec: ExecFn = execFileText): Promise<boolean> {
  const r = await exec('git', ['--no-optional-locks', 'rev-parse', '--is-inside-work-tree'], { cwd: folder })
  return r.code === 0 && r.stdout.trim() === 'true'
}

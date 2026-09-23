import { execFile } from 'node:child_process'

/** `notFound`: o executável nem existe (ENOENT) - diferente de um que existe e falha. */
export type ExecResult = { code: number; stdout: string; stderr: string; notFound?: boolean }
export type ExecFn = (
  file: string,
  args: string[],
  opts?: { cwd?: string; timeoutMs?: number },
) => Promise<ExecResult>

/** Roda um executável com lista de argumentos (nunca shell). Nunca rejeita. */
export const execFileText: ExecFn = (file, args, opts = {}) =>
  new Promise((resolve) => {
    try {
      execFile(
        file,
        args,
        { cwd: opts.cwd, timeout: opts.timeoutMs ?? 5000, windowsHide: true, encoding: 'utf-8' },
        (err, stdout, stderr) => {
          if (!err) return resolve({ code: 0, stdout, stderr })
          const e = err as NodeJS.ErrnoException & { code?: number | string; killed?: boolean }
          if (e.killed) return resolve({ code: -1, stdout, stderr: 'tempo esgotado' })
          if (e.code === 'ENOENT') return resolve({ code: -1, stdout, stderr: stderr || e.message, notFound: true })
          resolve({ code: typeof e.code === 'number' ? e.code : -1, stdout, stderr: stderr || e.message })
        },
      )
    } catch (err) {
      // `execFile` pode lançar de forma síncrona para argumentos inválidos
      // (ex.: byte nulo em `file`/`args` → ERR_INVALID_ARG_VALUE). Isso não
      // pode virar rejeição: quebraria o contrato "nunca rejeita" de quem
      // consome `ExecFn` (ex.: `readGitHead`).
      resolve({ code: -1, stdout: '', stderr: String(err) })
    }
  })

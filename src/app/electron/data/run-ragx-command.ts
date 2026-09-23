import { spawn } from 'node:child_process'
import { ragxCommand } from '../system/ragx-exe'

const TIMEOUT_MS = 60_000

export function runRagxCommand(cwd: string, args: string[]): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = spawn(ragxCommand(), args, { cwd, windowsHide: true })
    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill()
      reject(new Error(`ragx ${args.join(' ')} excedeu o tempo limite de ${TIMEOUT_MS / 1000}s`))
    }, TIMEOUT_MS)

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8')
    })
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf-8')
    })
    child.on('error', (err) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(err)
    })
    child.on('close', (code: number) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      // `ragx security scan`/`ragx trial` podem sair com codigo != 0 mesmo
      // quando ha JSON valido no stdout (ex.: --fail-on high sai 1 quando ha
      // achados bloqueados). Isso e DADO, nao falha - so rejeita quando o
      // stdout genuinamente nao e JSON (comando nao encontrado, crash antes
      // de produzir saida, etc.), caso em que o codigo de saida importa para
      // a mensagem de erro.
      try {
        resolve(JSON.parse(stdout))
      } catch (err) {
        reject(
          new Error(
            code === 0
              ? `saída de "ragx ${args.join(' ')}" não é JSON válido: ${String(err)}`
              : `ragx ${args.join(' ')} saiu com código ${code}: ${stderr.slice(0, 500)}`,
          ),
        )
      }
    })
  })
}

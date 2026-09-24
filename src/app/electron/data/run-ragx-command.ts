import { spawn } from 'node:child_process'
import fs from 'node:fs'
import { StringDecoder } from 'node:string_decoder'
import { ragxCommand } from '../system/ragx-exe'

const TIMEOUT_MS = 60_000

function spawnError(err: NodeJS.ErrnoException, cmd: string, cwd: string): Error {
  if (err.code === 'ENOENT') {
    // Node também dá ENOENT quando é a pasta de trabalho que sumiu.
    return new Error(fs.existsSync(cwd) ? `Comando não encontrado: ${cmd}` : `Pasta não encontrada: ${cwd}`)
  }
  return err
}

export function runRagxCommand(cwd: string, args: string[], opts: { timeoutMs?: number } = {}): Promise<unknown> {
  const timeoutMs = opts.timeoutMs ?? TIMEOUT_MS
  return new Promise((resolve, reject) => {
    const cmd = ragxCommand()
    const child = spawn(cmd, args, { cwd, windowsHide: true })
    // `StringDecoder`: um caractere multibyte partido entre dois pedaços do
    // stream não vira lixo (o que `chunk.toString()` por pedaço fazia).
    const outDecoder = new StringDecoder('utf8')
    const errDecoder = new StringDecoder('utf8')
    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill()
      reject(new Error(`ragx ${args.join(' ')} excedeu o tempo limite de ${timeoutMs / 1000}s`))
    }, timeoutMs)

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += outDecoder.write(chunk)
    })
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += errDecoder.write(chunk)
    })
    child.on('error', (err: NodeJS.ErrnoException) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(spawnError(err, cmd, cwd))
    })
    child.on('close', (code: number) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      stdout += outDecoder.end()
      stderr += errDecoder.end()
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

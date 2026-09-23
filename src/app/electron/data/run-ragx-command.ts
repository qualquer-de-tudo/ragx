import { spawn } from 'node:child_process'

export function runRagxCommand(cwd: string, args: string[]): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = spawn('ragx', args, { cwd })
    let stdout = ''
    let stderr = ''

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8')
    })
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf-8')
    })
    child.on('error', reject)
    child.on('close', (code: number) => {
      if (code !== 0) {
        reject(new Error(`ragx ${args.join(' ')} saiu com código ${code}: ${stderr.slice(0, 500)}`))
        return
      }
      try {
        resolve(JSON.parse(stdout))
      } catch (err) {
        reject(new Error(`saída de "ragx ${args.join(' ')}" não é JSON válido: ${String(err)}`))
      }
    })
  })
}

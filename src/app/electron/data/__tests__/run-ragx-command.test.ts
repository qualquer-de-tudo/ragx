import { describe, expect, it, vi, beforeEach } from 'vitest'
import { EventEmitter } from 'node:events'

vi.mock('node:child_process', () => {
  const spawn = vi.fn()
  return { spawn, default: { spawn } }
})

import { spawn } from 'node:child_process'
import { runRagxCommand } from '../run-ragx-command'

function fakeChildProcess(stdout: string, exitCode: number) {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter
    stderr: EventEmitter
  }
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  queueMicrotask(() => {
    child.stdout.emit('data', Buffer.from(stdout))
    child.emit('close', exitCode)
  })
  return child
}

describe('runRagxCommand', () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset()
  })

  it('resolve com o JSON parseado do stdout quando o comando sai com codigo 0', async () => {
    vi.mocked(spawn).mockReturnValue(fakeChildProcess('{"ok": true, "n": 3}\n', 0) as never)

    const result = await runRagxCommand('C:\\projeto', ['trial', '--json'])

    expect(result).toEqual({ ok: true, n: 3 })
    expect(spawn).toHaveBeenCalledWith('ragx', ['trial', '--json'], { cwd: 'C:\\projeto' })
  })

  it('rejeita quando o comando sai com codigo diferente de zero', async () => {
    vi.mocked(spawn).mockReturnValue(fakeChildProcess('', 1) as never)

    await expect(runRagxCommand('C:\\projeto', ['trial', '--json'])).rejects.toThrow()
  })
})

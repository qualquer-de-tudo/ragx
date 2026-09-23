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
    expect(spawn).toHaveBeenCalledWith(expect.any(String), ['trial', '--json'], {
      cwd: 'C:\\projeto',
      windowsHide: true,
    })
  })

  it('rejeita quando o comando sai com codigo diferente de zero e stdout nao e JSON valido', async () => {
    vi.mocked(spawn).mockReturnValue(fakeChildProcess('', 1) as never)

    await expect(runRagxCommand('C:\\projeto', ['trial', '--json'])).rejects.toThrow()
  })

  it('resolve com o JSON do stdout mesmo quando o comando sai com codigo != 0 (regressao do bug critico)', async () => {
    // `ragx security scan --fail-on high` sai com codigo 1 quando ha achados
    // bloqueados, mesmo com JSON valido no stdout. Isso e dado, nao falha.
    const json = '{"blocked": [{"path": "x"}], "redacted": [], "scanned": 10}'
    vi.mocked(spawn).mockReturnValue(fakeChildProcess(json, 1) as never)

    const result = await runRagxCommand('C:\\projeto', ['security', 'scan', '.', '--json'])

    expect(result).toEqual({ blocked: [{ path: 'x' }], redacted: [], scanned: 10 })
  })

  it('rejeita quando o comando sai com codigo 0 mas o stdout nao e JSON valido', async () => {
    vi.mocked(spawn).mockReturnValue(fakeChildProcess('isso nao e json', 0) as never)

    await expect(runRagxCommand('C:\\projeto', ['trial', '--json'])).rejects.toThrow(/não é JSON válido/)
  })

  it('mata o processo e rejeita quando o comando excede o tempo limite', async () => {
    vi.useFakeTimers()
    try {
      const child = new EventEmitter() as EventEmitter & {
        stdout: EventEmitter
        stderr: EventEmitter
        kill: ReturnType<typeof vi.fn>
      }
      child.stdout = new EventEmitter()
      child.stderr = new EventEmitter()
      child.kill = vi.fn()
      // nunca emite 'close' - simula um processo travado
      vi.mocked(spawn).mockReturnValue(child as never)

      const promise = runRagxCommand('C:\\projeto', ['trial', '--json'])
      const assertion = expect(promise).rejects.toThrow(/tempo limite/)

      await vi.advanceTimersByTimeAsync(60_000)

      await assertion
      expect(child.kill).toHaveBeenCalledOnce()
    } finally {
      vi.useRealTimers()
    }
  })
})

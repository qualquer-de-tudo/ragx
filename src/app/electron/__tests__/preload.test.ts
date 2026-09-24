import { beforeAll, describe, expect, it, vi } from 'vitest'

const electron = vi.hoisted(() => ({
  exposed: new Map<string, unknown>(),
  invoke: vi.fn(async () => undefined),
  on: vi.fn(),
  removeListener: vi.fn(),
}))

vi.mock('electron', () => {
  const ipcRenderer = { invoke: electron.invoke, on: electron.on, removeListener: electron.removeListener }
  return {
    contextBridge: {
      exposeInMainWorld: (key: string, api: unknown) => {
        electron.exposed.set(key, api)
      },
    },
    ipcRenderer,
  }
})

type Bridge = Record<string, (...args: unknown[]) => unknown>

let ragx: Bridge

beforeAll(async () => {
  await import('../preload')
  ragx = electron.exposed.get('ragx') as Bridge
})

describe('preload', () => {
  it('expõe só a ponte ragx, com exatamente os métodos conhecidos', () => {
    expect([...electron.exposed.keys()]).toEqual(['ragx'])
    expect(Object.keys(ragx).sort()).toEqual(
      [
        'cancelJob',
        'discover',
        'enqueueJob',
        'getClaudeIntegration',
        'getConnections',
        'getIndexRuns',
        'getProjectStatus',
        'getSettings',
        'getSnapshot',
        'listJobs',
        'onConnections',
        'onJobs',
        'onSnapshot',
        'pickFolder',
        'runOllamaBenchmark',
        'runSecurityScan',
        'runTrial',
        'setClaudeIntegration',
        'setOnboardingDone',
      ].sort(),
    )
  })

  it('nenhum valor da ponte é o ipcRenderer ou um objeto (só funções)', () => {
    for (const value of Object.values(ragx)) {
      expect(typeof value).toBe('function')
    }
  })

  it('nenhum método da ponte usa o canal removido ragx:get-ollama-environment', async () => {
    electron.invoke.mockClear()
    await ragx.runOllamaBenchmark()
    await ragx.getConnections()
    expect(electron.invoke.mock.calls.map((c) => (c as unknown[])[0])).not.toContain('ragx:get-ollama-environment')
    expect(ragx.getOllamaEnvironment).toBeUndefined()
  })

  it('runOllamaBenchmark chama o canal certo sem repassar argumentos', async () => {
    electron.invoke.mockClear()
    await ragx.runOllamaBenchmark('x; rm -rf /')
    expect(electron.invoke).toHaveBeenCalledWith('ragx:run-ollama-benchmark')
  })

  it('o interruptor do Claude Code usa os canais certos', async () => {
    electron.invoke.mockClear()
    await ragx.getClaudeIntegration()
    await ragx.setClaudeIntegration(false)
    expect(electron.invoke).toHaveBeenNthCalledWith(1, 'ragx:getClaudeIntegration')
    expect(electron.invoke).toHaveBeenNthCalledWith(2, 'ragx:setClaudeIntegration', false)
  })
})

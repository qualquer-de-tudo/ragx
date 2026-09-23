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
        'getConnections',
        'getOllamaEnvironment',
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
        'setOnboardingDone',
      ].sort(),
    )
  })

  it('nenhum valor da ponte é o ipcRenderer ou um objeto (só funções)', () => {
    for (const value of Object.values(ragx)) {
      expect(typeof value).toBe('function')
    }
  })

  it('getOllamaEnvironment chama o canal certo sem repassar argumentos', async () => {
    electron.invoke.mockClear()
    await ragx.getOllamaEnvironment('C:/Windows', { x: 1 })
    expect(electron.invoke).toHaveBeenCalledWith('ragx:get-ollama-environment')
  })

  it('runOllamaBenchmark chama o canal certo sem repassar argumentos', async () => {
    electron.invoke.mockClear()
    await ragx.runOllamaBenchmark('x; rm -rf /')
    expect(electron.invoke).toHaveBeenCalledWith('ragx:run-ollama-benchmark')
  })
})

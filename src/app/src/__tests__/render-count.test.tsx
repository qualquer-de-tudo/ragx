import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import type { ActivityEvent, ProjectSnapshot, Snapshot } from '../types/ragx-bridge'
import { installBridge, snap } from '../test/snap'

// `ProjectNumbers` é filho do `ProjectCard` sem memo: renderiza exatamente quando o card renderiza.
// `Sidebar` é filho direto do `App` (na casca): renderiza exatamente quando o `App` renderiza.
const counts = vi.hoisted(() => ({ card: 0, app: 0 }))

vi.mock('../components/project/ProjectBits', async (orig) => {
  const mod = await orig<typeof import('../components/project/ProjectBits')>()
  return {
    ...mod,
    ProjectNumbers: (p: Parameters<typeof mod.ProjectNumbers>[0]) => {
      counts.card++
      return mod.ProjectNumbers(p)
    },
  }
})
vi.mock('../components/shell/Sidebar', async (orig) => {
  const mod = await orig<typeof import('../components/shell/Sidebar')>()
  return {
    ...mod,
    Sidebar: (p: Parameters<typeof mod.Sidebar>[0]) => {
      counts.app++
      return mod.Sidebar(p)
    },
  }
})

import App from '../App'

const T0 = Date.parse('2026-10-01T12:00:00Z')

function projects(n: number): ProjectSnapshot[] {
  return Array.from({ length: n }, (_, i) =>
    snap({
      id: `p${i}`,
      name: `Projeto ${String(i).padStart(2, '0')}`,
      path: `C:/work/p${i}`,
      index: { finishedAt: new Date(T0 - 2 * 60_000).toISOString(), mode: 'incremental', source: 'cli', branch: 'main', commit: 'c1' },
    }),
  )
}

function snapshot(list: ProjectSnapshot[], generatedAt: number): Snapshot {
  // Cópia profunda: o IPC entrega objetos novos a cada push, mesmo com o conteúdo igual.
  return { projects: structuredClone(list), generatedAt: new Date(generatedAt).toISOString(), connectionsHealth: 'ok' }
}

async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('renderizações com os dados parados', () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: T0, toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    counts.card = 0
    counts.app = 0
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  function mount(list: ProjectSnapshot[], activity: ActivityEvent[] = []) {
    let push: (s: Snapshot) => void = () => {}
    installBridge({
      getSnapshot: vi.fn().mockResolvedValue(snapshot(list, T0)),
      onSnapshot: vi.fn((cb: (s: Snapshot) => void) => {
        push = cb
        return () => {}
      }),
      getActivity: vi.fn().mockResolvedValue(activity),
    })
    render(<App />)
    return { push: (s: Snapshot) => act(() => push(s)) }
  }

  it('12 projetos parados por 60 s: os cards renderizam só na montagem e o App não renderiza de novo', async () => {
    const list = projects(12)
    const { push } = mount(list)
    await settle()
    expect(screen.getAllByRole('article')).toHaveLength(12)
    const cardsNaMontagem = counts.card
    counts.app = 0

    // Um push do processo principal a cada 5 s, sempre com o mesmo conteúdo.
    for (let t = 5000; t <= 60_000; t += 5000) {
      await advance(5000)
      await push(snapshot(list, T0 + t))
    }
    console.log(`[0175] cards na montagem=${cardsNaMontagem} cards em 60 s=${counts.card} App em 60 s=${counts.app}`)
    expect(counts.card).toBeLessThanOrEqual(12)
    expect(counts.app).toBeLessThanOrEqual(1)
  })

  it('muda um projeto: só o card dele renderiza', async () => {
    const list = projects(12)
    const { push } = mount(list)
    await settle()
    counts.card = 0

    const next = structuredClone(list)
    next[3].telemetry = { ...next[3].telemetry, totalCalls: 42 }
    await push(snapshot(next, T0 + 5000))

    expect(counts.card).toBe(1)
    expect(within(screen.getAllByRole('article')[3]).getByText('42')).toBeInTheDocument()
  })

  it('"Indexado há N min" avança sozinho, sem snapshot novo', async () => {
    mount(projects(2))
    await settle()
    expect(screen.getAllByText('Indexado há 2 min')).toHaveLength(2)
    await advance(60_000)
    expect(screen.getAllByText('Indexado há 3 min')).toHaveLength(2)
    expect(screen.queryByText('Indexado há 2 min')).not.toBeInTheDocument()
  })

  it('"em uso agora" apaga um minuto depois do último evento', async () => {
    const evento: ActivityEvent = {
      id: 'e1', ts: new Date(T0).toISOString(), projectId: 'p0', projectName: 'Projeto 00',
      kind: 'mcp', name: 'search_hybrid', ms: 12, ok: true,
    } as ActivityEvent
    mount(projects(2), [evento])
    await settle()
    expect(screen.getAllByText('em uso agora').length).toBeGreaterThan(0)
    await advance(70_000)
    expect(screen.queryByText('em uso agora')).not.toBeInTheDocument()
  })
})

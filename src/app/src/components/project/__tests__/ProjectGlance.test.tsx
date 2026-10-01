import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ProjectGlance } from '../ProjectGlance'
import { installBridge, job, snap } from '../../../test/snap'
import type { StatusView } from '../../../projectStatus'
import type { ProjectState } from '../../../state'
import type { JobView, ProjectSnapshot } from '../../../types/ragx-bridge'

const NOW = '2026-10-01T12:00:00Z'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(NOW))
  installBridge()
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const ok = (state: 'fresh' | 'stale' | 'unknown', reasons: unknown[] = []): StatusView =>
  ({
    phase: 'ok',
    status: { initialized: true, documents: 1, chunks: 1, embeddings: 1, freshness: { state, current: null, reasons }, runs: [] },
  }) as unknown as StatusView

function glance(over: {
  project?: ProjectSnapshot
  state?: ProjectState
  status?: StatusView
  live?: boolean
  jobs?: JobView[]
  onSeeSavings?: () => void
} = {}) {
  return render(
    <ProjectGlance
      project={over.project ?? snap()}
      state={over.state ?? 'ok'}
      status={over.status ?? ok('fresh')}
      live={over.live ?? false}
      jobs={over.jobs ?? []}
      onSeeSavings={over.onSeeSavings ?? (() => {})}
    />,
  )
}

const block = (name: string) => within(screen.getByRole('group', { name }))

describe('ProjectGlance: está em dia?', () => {
  it('em dia', () => {
    glance()
    expect(block('Está em dia?').getByText('Índice em dia.')).toBeInTheDocument()
    expect(block('Está em dia?').queryByRole('button')).not.toBeInTheDocument() // estado ok: nada a fazer
  })

  it('defasado: o primeiro motivo em texto e o botão da ação', () => {
    glance({
      state: 'stale',
      status: ok('stale', [{ kind: 'commits_since_index', count: 3 }, { kind: 'uncommitted_changes', count: 1 }]),
    })
    const b = block('Está em dia?')
    expect(b.getByText(/Índice defasado: 3 commit\(s\) depois da última indexação\./)).toBeInTheDocument()
    expect(b.queryByText(/arquivo\(s\) alterado/)).not.toBeInTheDocument() // só o primeiro
    expect(b.getByRole('button', { name: 'Atualizar' })).toBeEnabled()
  })

  it('o botão enfileira o tipo certo e some a ação com tarefa na fila', () => {
    const b = installBridge()
    const { unmount } = glance({ state: 'stale', status: ok('stale') })
    fireEvent.click(block('Está em dia?').getByRole('button', { name: 'Atualizar' }))
    expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'update', projectId: 'p1' })
    unmount()
    glance({ state: 'stale', status: ok('stale'), jobs: [job({ kind: 'update', projectId: 'p1', state: 'queued' })] })
    expect(block('Está em dia?').getByRole('button', { name: /na fila/i })).toBeDisabled()
  })

  it('verificando', () => {
    glance({ status: { phase: 'loading' } })
    expect(block('Está em dia?').getByText('Verificando…')).toBeInTheDocument()
  })

  it('erro e desconhecido têm texto próprio', () => {
    glance({ status: { phase: 'error', message: 'timeout' } })
    expect(block('Está em dia?').getByText(/Sem resposta do ragx status/)).toBeInTheDocument()
    cleanup()
    glance({ status: ok('unknown') })
    expect(block('Está em dia?').getByText(/Estado do índice desconhecido/)).toBeInTheDocument()
  })
})

describe('ProjectGlance: economia (14 dias)', () => {
  it('com medição: percentual, tokens e o botão que abre a aba', () => {
    const onSeeSavings = vi.fn()
    glance({
      project: snap({
        telemetry: {
          callsByTool: [], totalCalls: 5, tokensDelivered: 1000, lastCallAt: null,
          savings: { days: [], baseline: 10_000, delivered: 1_000, calls: 5 },
        },
      }),
      onSeeSavings,
    })
    expect(block('Economia (14 dias)').getByText(/90% menos tokens, 9\.000 economizados\./)).toBeInTheDocument()
    fireEvent.click(block('Economia (14 dias)').getByRole('button', { name: 'Ver gráfico' }))
    expect(onSeeSavings).toHaveBeenCalledTimes(1)
  })

  it('sem medição: "Sem medição ainda", nunca 0%', () => {
    glance()
    const b = block('Economia (14 dias)')
    expect(b.getByText('Sem medição ainda.')).toBeInTheDocument()
    expect(b.queryByText(/0%/)).not.toBeInTheDocument()
  })
})

describe('ProjectGlance: agente usando?', () => {
  it('em uso agora', () => {
    glance({ live: true })
    expect(block('Agente usando?').getByText(/Em uso agora: o agente chamou o RAGX no último minuto\./)).toBeInTheDocument()
  })

  it('última chamada e total de 24 h', () => {
    glance({
      project: snap({
        telemetry: { callsByTool: [], totalCalls: 12, tokensDelivered: 0, lastCallAt: '2026-10-01T09:00:00Z' },
      }),
    })
    expect(block('Agente usando?').getByText(/Última chamada há 3 h, 12 chamada\(s\) em 24 h\./)).toBeInTheDocument()
  })

  it('nenhuma chamada manda conferir em Conexões', () => {
    glance()
    expect(block('Agente usando?').getByText(/Nenhuma chamada registrada\. Confira em Conexões/)).toBeInTheDocument()
  })
})

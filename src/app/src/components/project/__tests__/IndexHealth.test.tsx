import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { IndexHealth } from '../IndexHealth'
import { installBridge, snap } from '../../../test/snap'
import type { IndexRun, ProjectStatus } from '../../../projectStatus'

let n = 0
const run = (over: Partial<IndexRun> = {}): IndexRun => {
  n += 1
  return {
    key: `r${n}`, startedAt: '2026-10-01T10:00:00Z', finishedAt: '2026-10-01T10:00:02Z', mode: 'incremental', source: 'cli', branch: null,
    commit: null, indexed: 0, durationMs: 2000, filesSeen: 1, blocked: 0, embedded: 0, error: null, ...over,
  }
}
const status = (runs: IndexRun[]): ProjectStatus => ({ freshness: { state: 'fresh', reasons: [] }, runs })

beforeEach(() => installBridge())
afterEach(cleanup)

describe('IndexHealth', () => {
  it('poucos dados: texto de tendência com a contagem e gráfico com tabela alternativa', () => {
    render(<IndexHealth project={snap()} status={status([run({ durationMs: 1500 }), run({ durationMs: 3000, error: 'x' })])} jobs={[]} />)
    expect(screen.getByText(/poucos dados para tendência \(2 de 6 indexações\)/)).toBeInTheDocument()
    const chart = screen.getByRole('group', { name: 'Duração das últimas indexações' })
    const bars = within(chart).getAllByRole('img')
    expect(bars).toHaveLength(2)
    expect(bars.map((b) => b.getAttribute('aria-label'))).toEqual([expect.stringContaining('3 s, falhou'), expect.stringContaining('1,5 s')])
    const details = screen.getByText('Ver em tabela').closest('details')!
    expect(within(details).getByRole('table')).toBeInTheDocument()
  })

  it('o nível aparece em texto no selo e nas checagens', () => {
    render(<IndexHealth project={snap({ hooksInstalled: false })} status={status([run()])} jobs={[]} />)
    expect(screen.getAllByText('Atenção').length).toBeGreaterThan(0)
    expect(screen.getByText(/Hooks de git ausentes/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Instalar hooks' })).toBeInTheDocument()
  })

  it('o erro da última indexação deixa "Com problema"', () => {
    render(<IndexHealth project={snap()} status={status([run({ error: 'embedder fora' }), run({ error: 'y' })])} jobs={[]} />)
    expect(screen.getAllByText('Com problema').length).toBeGreaterThan(0)
    expect(screen.getByText(/A última indexação falhou: embedder fora/)).toBeInTheDocument()
    expect(screen.getByText(/O índice está falhando/)).toBeInTheDocument()
  })

  it('sem duração em nenhuma indexação: "sem dado de duração" e nada de gráfico', () => {
    const runs = [run({ durationMs: null, startedAt: null, finishedAt: null }), run({ durationMs: null, startedAt: null, finishedAt: null })]
    render(<IndexHealth project={snap()} status={status(runs)} jobs={[]} />)
    expect(screen.getByText(/sem dado de duração/)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Duração das últimas indexações' })).not.toBeInTheDocument()
  })

  it('status ausente diz "sem dado" e nunca "terminou sem erro"', () => {
    render(<IndexHealth project={snap()} status={null} jobs={[]} />)
    expect(screen.getByText(/Última indexação: sem dado/)).toBeInTheDocument()
    expect(screen.queryByText(/terminou sem erro/)).not.toBeInTheDocument()
  })
})


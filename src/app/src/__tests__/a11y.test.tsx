import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react'
import axe from 'axe-core'
import { ProjectsPage } from '../pages/ProjectsPage'
import { ProjectPage } from '../pages/ProjectPage'
import { ActivityPage } from '../pages/ActivityPage'
import { ConnectionsPage } from '../pages/ConnectionsPage'
import { rememberProjectTab, type ProjectTab } from '../projectTab'
import { connectionChecks, installBridge, job, snap } from '../test/snap'
import type { ActivityEvent } from '../types/ragx-bridge'

// RAGX-0185: 0 violações `serious` e `critical` do axe nas telas principais. `color-contrast` fica desligado: o jsdom
// não calcula cor de verdade (o contraste é da RAGX-0178, com teste próprio por token).
async function violations(container: HTMLElement) {
  const result = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    resultTypes: ['violations'],
  })
  return result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
}

function expectClean(list: Awaited<ReturnType<typeof violations>>) {
  expect(list.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([])
}

const status = {
  initialized: true, documents: 3, chunks: 10, embeddings: 10,
  freshness: { state: 'fresh', current: { branch: 'main', commit: 'c1', dirty: false }, reasons: [] }, recent_runs: [],
}

const event = (i: number): ActivityEvent =>
  ({
    id: `e${i}`, ts: new Date(Date.now() - i * 1000).toISOString(), projectId: 'p1', projectName: 'p1', kind: 'mcp',
    name: 'build_context', ms: 12, ok: true, tokensDelivered: 100, baselineTokens: 900, errCode: null, respChars: 10,
    respTokens: 3, client: 'claude-code', profile: null, session: null,
  }) as ActivityEvent

beforeEach(() => {
  installBridge({ getProjectStatus: vi.fn().mockResolvedValue(status), getIndexRuns: vi.fn().mockResolvedValue({ runs: [], total: 0 }) })
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  rememberProjectTab('geral')
  vi.restoreAllMocks()
})

describe('axe: sem violações serious ou critical', () => {
  it('Projetos (grade e lista)', async () => {
    const projects = [snap({ id: 'a', name: 'A' }), snap({ id: 'b', name: 'B', hooksInstalled: false })]
    const { container } = render(<ProjectsPage projects={projects} jobs={[job({ projectId: 'a' })]} query="" onOpen={vi.fn()} />)
    expectClean(await violations(container))
    fireEvent.click(screen.getByRole('radio', { name: 'Lista' }))
    expectClean(await violations(container))
    fireEvent.click(screen.getByRole('radio', { name: 'Grade' }))
  })

  it.each([
    ['geral', 'Visão geral'],
    ['economia', 'Economia de tokens'],
    ['historico', 'Histórico'],
    ['manutencao', 'Manutenção'],
  ] as Array<[ProjectTab, string]>)('Detalhe, aba %s', async (aba) => {
    rememberProjectTab(aba)
    const { container } = render(<ProjectPage project={snap({ id: 'p1', name: 'p1' })} jobs={[]} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.queryByText('Verificando…')).not.toBeInTheDocument())
    expectClean(await violations(container))
  })

  it('Atividade', async () => {
    const { container } = render(
      <ActivityPage events={[event(1), event(2)]} projects={[snap({ id: 'p1', name: 'p1' })]} jobs={[]} now={Date.now()} onOpen={vi.fn()} />,
    )
    expectClean(await violations(container))
  })

  it('Conexões', async () => {
    const { container } = render(<ConnectionsPage connections={connectionChecks()} checking={false} onRefresh={vi.fn()} jobs={[]} />)
    expectClean(await violations(container))
  })

  it('a varredura enxerga um erro de verdade (não está vazia)', async () => {
    const { container } = render(<button type="button" />)
    const list = await violations(container)
    expect(list.map((v) => v.id)).toContain('button-name')
  })
})

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ActivityPage } from '../ActivityPage'
import { liveProjectIds, mergeEvents, whoLabel } from '../../activity'
import { job, snap } from '../../test/snap'
import type { ActivityEvent } from '../../types/ragx-bridge'

const NOW = Date.parse('2026-09-29T20:00:00Z')

function ev(over: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    id: Math.random().toString(36).slice(2),
    ts: '2026-09-29T19:59:40Z',
    projectId: 'p1',
    projectName: 'Juriflux',
    kind: 'mcp',
    name: 'build_context',
    ms: 6375,
    ok: null,
    tokensDelivered: 2436,
    baselineTokens: 26290,
    errCode: null,
    respChars: null,
    respTokens: null,
    client: 'claude-code',
    profile: 'empresa',
    session: 'abcd1234',
    ...over,
  }
}

describe('atividade: regras', () => {
  it('junta sem repetir, do mais novo para o mais antigo, e descarta o que passou de 24 h', () => {
    const a = ev({ id: 'a', ts: '2026-09-29T19:00:00Z' })
    const b = ev({ id: 'b', ts: '2026-09-29T19:30:00Z' })
    const velho = ev({ id: 'v', ts: '2026-09-28T10:00:00Z' })
    expect(mergeEvents([a], [b, a, velho], NOW).map((e) => e.id)).toEqual(['b', 'a'])
  })

  it('"em uso agora" vale por um minuto', () => {
    const eventos = [ev({ projectId: 'p1', ts: '2026-09-29T19:59:30Z' }), ev({ projectId: 'p2', ts: '2026-09-29T19:58:00Z' })]
    expect([...liveProjectIds(eventos, NOW)]).toEqual(['p1'])
  })

  it('quem: perfil do Claude, terminal do Claude, terminal, agente sem nome', () => {
    expect(whoLabel(ev())).toBe('Claude Code · empresa')
    expect(whoLabel(ev({ kind: 'cli', name: 'search' }))).toBe('Terminal do Claude · empresa')
    expect(whoLabel(ev({ kind: 'cli', name: 'search', client: null, profile: null }))).toBe('Terminal')
    expect(whoLabel(ev({ client: null, profile: null }))).toBe('Agente MCP')
  })
})

function renderPage(events: ActivityEvent[], over: Partial<Parameters<typeof ActivityPage>[0]> = {}) {
  const onOpen = vi.fn()
  render(
    <ActivityPage
      events={events}
      projects={[snap({ id: 'p1', name: 'Juriflux' }), snap({ id: 'p2', name: 'ragx' })]}
      jobs={[]}
      now={NOW}
      onOpen={onOpen}
      {...over}
    />,
  )
  return { onOpen }
}

describe('ActivityPage', () => {
  it('sem eventos, explica de onde a atividade vem', () => {
    renderPage([])
    expect(screen.getByText(/Nenhuma atividade nas últimas 24 h/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('nada no último minuto')
  })

  it('mostra o evento com quem, o quê, onde, tokens e tempo; clicar no projeto abre o projeto', () => {
    const { onOpen } = renderPage([ev()])
    const item = screen.getByRole('listitem')
    expect(within(item).getByText('build_context')).toBeInTheDocument()
    expect(within(item).getByText('Claude Code · empresa')).toBeInTheDocument()
    expect(within(item).getByText(/2\.436 de 26\.290 tokens \(−91%\) · 6,4 s/)).toBeInTheDocument()
    fireEvent.click(within(item).getByRole('button', { name: 'Juriflux' }))
    expect(onOpen).toHaveBeenCalledWith('p1')
    expect(screen.getByRole('status')).toHaveTextContent('Em uso agora')
  })

  it('resume o dia: chamadas, sessões, comandos, economia e projetos em uso', () => {
    renderPage([
      ev({ id: '1' }),
      ev({ id: '2', kind: 'session', name: 'session_start', tokensDelivered: null, baselineTokens: null }),
      ev({ id: '3', kind: 'cli', name: 'search', projectId: 'p2', projectName: 'ragx', tokensDelivered: null, baselineTokens: null }),
    ])
    expect(screen.getByText('Chamadas MCP').nextSibling).toHaveTextContent('1')
    expect(screen.getByText('Sessões do Claude').nextSibling).toHaveTextContent('1')
    expect(screen.getByText('1 comando(s) no terminal')).toBeInTheDocument()
    expect(screen.getByText('91% menos que ler os arquivos')).toBeInTheDocument()
    expect(screen.getByText('Projetos em uso').nextSibling).toHaveTextContent('2')
  })

  it('filtra por tipo e por projeto', () => {
    renderPage([
      ev({ id: '1', name: 'build_context' }),
      ev({ id: '2', kind: 'cli', name: 'search', projectId: 'p2', projectName: 'ragx' }),
    ])
    fireEvent.click(screen.getByRole('radio', { name: 'Terminal' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText('ragx search')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: 'Tudo' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'p1' } })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText('build_context')).toBeInTheDocument()
  })

  it('"Em andamento" mostra indexação disparada por hook e tarefa rodando na fila', () => {
    renderPage([], {
      projects: [
        snap({ id: 'p1', name: 'Juriflux', running: { source: 'hook:post-commit', startedAt: '2026-09-29T19:59:00Z' } }),
        snap({ id: 'p2', name: 'ragx' }),
      ],
      jobs: [job({ projectId: 'p2', label: 'Gerar embeddings em ragx', state: 'running' })],
    })
    const card = within(screen.getByRole('region', { name: 'Em andamento' }))
    expect(card.getByText('Indexando · Commit')).toBeInTheDocument()
    expect(card.getByText('Gerar embeddings em ragx')).toBeInTheDocument()
  })
})

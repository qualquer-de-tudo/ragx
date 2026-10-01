import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ActivityPage } from '../pages/ActivityPage'
import { snap, installBridge } from '../test/snap'
import type { ActivityEvent } from '../types/ragx-bridge'

// "Sessões" também é um filtro de tipo: o rádio da VISÃO é o do grupo "Visão"
const visao = (nome: string) => within(screen.getByRole('radiogroup', { name: 'Visão' })).getByRole('radio', { name: nome })

const NOW = Date.parse('2026-10-01T10:30:00Z')
let n = 0
function ev(over: Partial<ActivityEvent> = {}): ActivityEvent {
  n += 1
  return {
    id: `e${n}`, ts: '2026-10-01T10:00:00Z', projectId: 'p1', projectName: 'Juriflux', kind: 'mcp', name: 'build_context',
    ms: 100, ok: null, tokensDelivered: 3000, baselineTokens: 9000, errCode: null, respChars: null, respTokens: null,
    client: 'claude-code', profile: 'empresa', session: 'abcd1234', ...over,
  }
}

function page(events: ActivityEvent[]) {
  installBridge()
  return render(
    <ActivityPage events={events} projects={[snap({ id: 'p1', name: 'Juriflux' }), snap({ id: 'p2', name: 'Outro' })]} jobs={[]} now={NOW} onOpen={vi.fn()} />,
  )
}

afterEach(() => {
  // a visão escolhida vale até fechar o painel: volta ao padrão para o próximo teste
  const grupo = screen.queryByRole('radiogroup', { name: 'Visão' })
  if (grupo) fireEvent.click(within(grupo).getByRole('radio', { name: 'Eventos' }))
  cleanup()
})

const events = [
  ev({ ts: '2026-10-01T10:00:00Z', kind: 'session', name: 'session_start', tokensDelivered: null, baselineTokens: null }),
  ev({ ts: '2026-10-01T10:01:00Z', kind: 'session', name: 'session_start', tokensDelivered: null, baselineTokens: null }),
  ev({ ts: '2026-10-01T10:02:00Z' }),
  ev({ ts: '2026-10-01T10:03:00Z', ok: false, errCode: 'not_found', respChars: 1234 }),
  ev({ ts: '2026-10-01T10:10:00Z', session: 'zzzz9999', projectId: 'p2', projectName: 'Outro', kind: 'cli', name: 'search' }),
]

describe('Atividade: visão Sessões', () => {
  it('o padrão é Eventos e alternar mostra uma linha por sessão com cabeçalho e resumo em texto', () => {
    page(events)
    expect(visao('Eventos')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('list', { name: /Eventos, do mais novo/ })).toBeInTheDocument()
    fireEvent.click(visao('Sessões'))
    const list = screen.getByRole('list', { name: /Sessões, da mais recente/ })
    expect(within(list).getAllByRole('button')).toHaveLength(2) // abcd1234 e zzzz9999
    expect(screen.getByText(/Claude Code · empresa · Juriflux · sessão abcd1234 · /)).toBeInTheDocument()
    expect(screen.getByText(/2 chamada\(s\) MCP, 0 comando\(s\) ragx, .* usou o RAGX, 2 inícios de contexto \(subagentes\), 1 falha\(s\)/)).toBeInTheDocument()
  })

  it('log sem ok mostra "falhas: sem dado", nunca "0 falha(s)"', () => {
    page([ev({ session: 'semok0001' })])
    fireEvent.click(visao('Sessões'))
    expect(screen.getByText(/falhas: sem dado/)).toBeInTheDocument()
    expect(screen.queryByText(/0 falha\(s\)/)).not.toBeInTheDocument()
  })

  it('evento sem sessão cai em "Sem sessão identificada"', () => {
    page([ev({ session: null })])
    fireEvent.click(visao('Sessões'))
    expect(screen.getByText(/Sem sessão identificada/)).toBeInTheDocument()
  })

  it('o botão abre e fecha os eventos (aria-expanded) e mostra código do erro e tamanho da resposta', () => {
    page(events)
    fireEvent.click(visao('Sessões'))
    const btn = screen.getByRole('button', { name: /sessão abcd1234/ })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'true')
    expect(btn.getAttribute('aria-controls')).toBeTruthy()
    expect(screen.getByText(/falhou \(not_found\)/)).toBeInTheDocument()
    expect(screen.getByText(/1\.234 caracteres na resposta/)).toBeInTheDocument()
    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'false')
  })

  it('o filtro de projeto vale na visão Sessões', () => {
    page(events)
    fireEvent.click(visao('Sessões'))
    fireEvent.change(screen.getByRole('combobox', { name: 'Projeto' }), { target: { value: 'p2' } })
    expect(screen.queryByText(/sessão abcd1234/)).not.toBeInTheDocument()
    expect(screen.getByText(/sessão zzzz9999/)).toBeInTheDocument()
  })

  it('com 500 eventos avisa que sessões antigas podem estar incompletas (só na visão Sessões)', () => {
    const many = Array.from({ length: 500 }, (_, i) => ev({ ts: `2026-10-01T10:${String(i % 60).padStart(2, '0')}:00Z`, session: `s${i % 7}` }))
    page(many)
    expect(screen.queryByText(/500 eventos mais recentes/)).not.toBeInTheDocument()
    fireEvent.click(visao('Sessões'))
    expect(screen.getByText(/Mostrando os 500 eventos mais recentes; sessões antigas podem estar incompletas/)).toBeInTheDocument()
  })
})

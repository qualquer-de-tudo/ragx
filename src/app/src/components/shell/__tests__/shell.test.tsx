import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { Sidebar } from '../Sidebar'
import { QueueIndicator } from '../QueueIndicator'
import { Badge } from '../Badge'
import { TopBar } from '../TopBar'
import type { JobView } from '../../../types/ragx-bridge'

function job(over: Partial<JobView> = {}): JobView {
  return {
    id: 'j1',
    kind: 'embed',
    label: 'Gerar embeddings em Juriflux',
    projectId: 'juriflux',
    model: null,
    state: 'running',
    step: 1,
    steps: 1,
    phase: 'embed',
    done: 40,
    total: 100,
    etaSeconds: 120,
    ratePerSecond: 2,
    note: null,
    error: null,
    logTail: [],
    queuedAt: '2026-09-23T10:00:00Z',
    startedAt: '2026-09-23T10:00:01Z',
    finishedAt: null,
    ...over,
  }
}

describe('Sidebar', () => {
  it('mostra os três itens com texto e marca a página ativa', () => {
    render(<Sidebar route={{ page: 'connections' }} onNavigate={() => {}} />)
    const nav = screen.getByRole('navigation')
    expect(within(nav).getByRole('button', { name: 'Projetos' })).not.toHaveAttribute('aria-current')
    expect(within(nav).getByRole('button', { name: 'Conexões' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('button', { name: 'Como funciona' })).not.toHaveAttribute('aria-current')
  })

  it('o detalhe de um projeto conta como a página Projetos', () => {
    render(<Sidebar route={{ page: 'project', id: 'x' }} onNavigate={() => {}} />)
    expect(screen.getByRole('button', { name: 'Projetos' })).toHaveAttribute('aria-current', 'page')
  })

  it('navega ao clicar', () => {
    const onNavigate = vi.fn()
    render(<Sidebar route={{ page: 'projects' }} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByRole('button', { name: 'Como funciona' }))
    expect(onNavigate).toHaveBeenCalledWith({ page: 'how' })
    fireEvent.click(screen.getByRole('button', { name: 'Conexões' }))
    expect(onNavigate).toHaveBeenCalledWith({ page: 'connections' })
  })
})

describe('QueueIndicator', () => {
  it('diz "Nenhuma tarefa" com a fila vazia', () => {
    render(<QueueIndicator jobs={[]} onCancel={() => {}} />)
    expect(screen.getByRole('button', { name: /Nenhuma tarefa/ })).toBeInTheDocument()
  })

  it('conta só as tarefas ativas, no singular e no plural', () => {
    const { rerender } = render(
      <QueueIndicator jobs={[job(), job({ id: 'old', state: 'done' })]} onCancel={() => {}} />,
    )
    expect(screen.getByRole('button', { name: /^1 tarefa$/ })).toBeInTheDocument()

    rerender(
      <QueueIndicator
        jobs={[job(), job({ id: 'j2', state: 'queued' }), job({ id: 'j3', state: 'queued' })]}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: /^3 tarefas$/ })).toBeInTheDocument()
  })

  it('aberto, mostra estado, progresso, previsão e cancela pelo id', () => {
    const onCancel = vi.fn()
    render(
      <QueueIndicator
        jobs={[
          job(),
          job({ id: 'j9', label: 'Atualizar RAGX', state: 'failed', error: 'ragx saiu com código 1', etaSeconds: null }),
        ]}
        onCancel={onCancel}
      />,
    )
    const trigger = screen.getByRole('button', { name: '1 tarefa' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    const dialog = screen.getByRole('dialog', { name: 'Tarefas' })
    expect(within(dialog).getByText('Gerar embeddings em Juriflux')).toBeInTheDocument()
    expect(within(dialog).getByText('Rodando')).toBeInTheDocument()
    expect(within(dialog).getByText('Falhou')).toBeInTheDocument()
    expect(within(dialog).getByText('ragx saiu com código 1')).toBeInTheDocument()
    expect(within(dialog).getByText('Faltam cerca de 2 min')).toBeInTheDocument()
    expect(within(dialog).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')

    // Só a ativa tem "Cancelar".
    const cancel = within(dialog).getAllByRole('button', { name: 'Cancelar' })
    expect(cancel).toHaveLength(1)
    fireEvent.click(cancel[0])
    expect(onCancel).toHaveBeenCalledWith('j1')
  })

  it('mostra os rótulos de todos os estados e a nota', () => {
    render(
      <QueueIndicator
        jobs={[
          job({ id: 'a', state: 'queued', total: null, etaSeconds: null }),
          job({ id: 'b', state: 'done', note: 'Outra indexação estava rodando; este pedido ficou agendado.' }),
          job({ id: 'c', state: 'cancelled' }),
        ]}
        onCancel={() => {}}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '1 tarefa' }))
    const dialog = screen.getByRole('dialog', { name: 'Tarefas' })
    expect(within(dialog).getByText('Na fila')).toBeInTheDocument()
    expect(within(dialog).getByText('Concluída')).toBeInTheDocument()
    expect(within(dialog).getByText('Cancelada')).toBeInTheDocument()
    expect(
      within(dialog).getByText('Outra indexação estava rodando; este pedido ficou agendado.'),
    ).toBeInTheDocument()
  })

  it('fecha com Escape e devolve o foco ao botão', () => {
    render(<QueueIndicator jobs={[job()]} onCancel={() => {}} />)
    const trigger = screen.getByRole('button', { name: '1 tarefa' })
    fireEvent.click(trigger)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
})

describe('Badge', () => {
  it.each(['good', 'warning', 'critical', 'accent', 'muted'] as const)('tom %s sempre carrega texto', (tone) => {
    const { container } = render(<Badge tone={tone}>Atualizado</Badge>)
    const badge = container.querySelector('.badge')!
    expect(badge).toHaveClass(`badge-${tone}`)
    // O "●" é decorativo; o que sobra, tirando o ponto, é texto de verdade.
    expect(badge.textContent!.replace('●', '').trim()).toBe('Atualizado')
    expect(badge.querySelector('[aria-hidden="true"]')!.textContent).toBe('●')
  })
})

describe('TopBar', () => {
  const base = { query: '', onQuery: () => {}, jobs: [], onOpenConnections: () => {}, onCancelJob: () => {} }

  it.each([
    ['ok', 'Conexões: tudo certo'],
    ['warn', 'Conexões: atenção'],
    ['error', 'Conexões: com problema'],
  ] as const)('ponto de saúde %s tem aria-label com o estado', (health, label) => {
    render(<TopBar {...base} health={health} />)
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  })

  it('sem checagem ainda, não finge estar tudo certo', () => {
    render(<TopBar {...base} health={null} />)
    expect(screen.getByRole('button', { name: 'Conexões: verificando' })).toBeInTheDocument()
  })

  it('o ponto de saúde abre Conexões', () => {
    const onOpenConnections = vi.fn()
    render(<TopBar {...base} health="warn" onOpenConnections={onOpenConnections} />)
    fireEvent.click(screen.getByRole('button', { name: 'Conexões: atenção' }))
    expect(onOpenConnections).toHaveBeenCalledOnce()
  })

  it('a busca é controlada e tem placeholder "Buscar projeto"', () => {
    const onQuery = vi.fn()
    render(<TopBar {...base} health="ok" onQuery={onQuery} />)
    const input = screen.getByRole('searchbox', { name: 'Buscar projeto' })
    expect(input).toHaveAttribute('placeholder', 'Buscar projeto')
    fireEvent.change(input, { target: { value: 'juri' } })
    expect(onQuery).toHaveBeenCalledWith('juri')
  })
})

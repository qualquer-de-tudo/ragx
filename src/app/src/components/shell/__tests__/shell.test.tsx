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

  it('"Como funciona" fica no fim da barra, depois de todos os outros itens', () => {
    render(<Sidebar route={{ page: 'projects' }} onNavigate={() => {}} />)
    const nomes = within(screen.getByRole('navigation')).getAllByRole('button').map((b) => b.textContent)
    expect(nomes[nomes.length - 1]).toBe('Como funciona')
    expect(nomes.slice(0, -1)).toEqual(['Projetos', 'Atividade', 'Conexões', 'Preferências'])
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

describe('Sidebar: atividade', () => {
  it('tem o item Atividade, que acende quando há uso no último minuto', () => {
    const onNavigate = vi.fn()
    const { rerender } = render(<Sidebar route={{ page: 'activity' }} onNavigate={onNavigate} />)
    expect(screen.getByRole('button', { name: 'Atividade' })).toHaveAttribute('aria-current', 'page')
    rerender(<Sidebar route={{ page: 'projects' }} onNavigate={onNavigate} live />)
    fireEvent.click(screen.getByRole('button', { name: 'Atividade em uso agora' }))
    expect(onNavigate).toHaveBeenCalledWith({ page: 'activity' })
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
    // O glifo (nó + aresta) é decorativo e não tem texto; o texto do selo é só o estado, de verdade.
    expect(badge.textContent).toBe('Atualizado')
    const mark = badge.querySelector('.badge-mark')!
    expect(mark).toHaveAttribute('aria-hidden', 'true')
    expect(mark.textContent).toBe('')
    expect(badge.querySelector('.badge-text')).toHaveTextContent('Atualizado')
  })

  // A forma do nó diz o estado (ADR-0017): cada tom tem um desenho próprio, não só uma cor.
  const shapes = {
    good: { circle: 2, line: 0, path: 0, dashed: 0 }, // cheio com anel
    warning: { circle: 1, line: 0, path: 1, dashed: 0 }, // meio cheio
    critical: { circle: 1, line: 1, path: 0, dashed: 0 }, // cortado
    accent: { circle: 2, line: 0, path: 0, dashed: 1 }, // anel tracejado com ponto (em órbita)
    muted: { circle: 1, line: 0, path: 0, dashed: 0 }, // vazio
  } as const

  it.each(Object.keys(shapes) as Array<keyof typeof shapes>)('tom %s tem o glifo do seu estado', (tone) => {
    const { container } = render(<Badge tone={tone}>Estado</Badge>)
    const svg = container.querySelector('.badge-mark svg')!
    expect(svg).toHaveAttribute('aria-hidden', 'true')
    expect(svg).toHaveAttribute('data-state', tone)
    expect(svg).toHaveClass(`node-glyph-${tone}`)
    expect({
      circle: svg.querySelectorAll('circle').length,
      line: svg.querySelectorAll('line').length,
      path: svg.querySelectorAll('path').length,
      dashed: svg.querySelectorAll('[stroke-dasharray]').length,
    }).toEqual(shapes[tone])
    // Só o anel em órbita gira (e o CSS o para com prefers-reduced-motion).
    expect(svg.querySelectorAll('.node-glyph-orbit')).toHaveLength(tone === 'accent' ? 1 : 0)
  })

  it('o vazio (sem uso) e o cheio (em dia) não são o mesmo desenho', () => {
    const muted = render(<Badge tone="muted">a</Badge>).container.querySelector('svg')!.innerHTML
    const good = render(<Badge tone="good">b</Badge>).container.querySelector('svg')!.innerHTML
    expect(muted).not.toBe(good)
  })
})

describe('TopBar', () => {
  const base = {
    query: '',
    onQuery: () => {},
    jobs: [],
    onOpenConnections: () => {},
    onCancelJob: () => {},
  }

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

  it('concentra busca, fila e acesso a Conexões, sem interruptor de agente', () => {
    render(<TopBar {...base} health="ok" />)
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Conexões: tudo certo' })).toBeInTheDocument()
  })
})

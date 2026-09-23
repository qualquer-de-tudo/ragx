import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { ProjectsPage } from '../ProjectsPage'
import { installBridge, job, snap } from '../../test/snap'
import type { JobView, ProjectSnapshot } from '../../types/ragx-bridge'

// Um projeto por estado (a ordem das regras de `deriveProjectState` decide).
const ALL: ProjectSnapshot[] = [
  snap({ id: 'ok', name: 'Juriflux', path: 'C:/projects/aivon/juriflux' }),
  snap({ id: 'stale', name: 'São Paulo', path: 'C:/projects/clientes/sp', git: { branch: 'main', commit: 'c2' } }),
  snap({
    id: 'emb',
    name: 'Embedder',
    path: 'C:/projects/aivon/emb',
    counts: { documents: 3, chunks: 10, embeddings: 4, pendingEmbeddings: 6 },
  }),
  snap({ id: 'nohooks', name: 'Nohooks', path: 'C:/projects/aivon/nohooks', hooksInstalled: false }),
  snap({ id: 'err', name: 'Quebrado', path: 'C:/projects/aivon/quebrado', lastError: 'embedder fora' }),
  snap({ id: 'gone', name: 'Sumido', path: 'C:/projects/aivon/sumido', exists: false }),
  snap({ id: 'busy', name: 'Ocupado', path: 'C:/projects/aivon/ocupado' }),
]

const BUSY: JobView[] = [job({ id: 'jb', projectId: 'busy', kind: 'update', etaSeconds: 120, done: 40, total: 100 })]

function renderPage(over: { projects?: ProjectSnapshot[]; jobs?: JobView[]; query?: string } = {}) {
  const onOpen = vi.fn()
  const utils = render(
    <ProjectsPage projects={over.projects ?? ALL} jobs={over.jobs ?? BUSY} query={over.query ?? ''} onOpen={onOpen} />,
  )
  return { ...utils, onOpen }
}

const card = (name: string) => screen.getByRole('article', { name })

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-23T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ProjectsPage', () => {
  it('cada card mostra o selo e o botão do seu estado', () => {
    installBridge()
    renderPage()
    const expected: Array<[string, string, string]> = [
      ['Juriflux', 'Atualizado', 'Abrir'],
      ['São Paulo', 'Defasado', 'Atualizar agora'],
      ['Embedder', 'Embeddings faltando', 'Gerar embeddings'],
      ['Nohooks', 'Sem hooks', 'Instalar hooks'],
      ['Quebrado', 'Com problema', 'Ver detalhes'],
      ['Sumido', 'Pasta ausente', 'Ver detalhes'],
    ]
    for (const [name, badge, button] of expected) {
      const c = within(card(name))
      expect(c.getByText(badge).closest('.badge')).toHaveTextContent(`● ${badge}`)
      expect(c.getByRole('button', { name: button })).toBeEnabled()
    }
    const busy = within(card('Ocupado'))
    expect(busy.getByText('Indexando…', { selector: '.badge-text' })).toBeInTheDocument()
    expect(busy.getByRole('button', { name: 'Indexando…' })).toBeDisabled()
  })

  it('"Gerar embeddings" enfileira a tarefa do projeto sem abrir o detalhe', () => {
    const b = installBridge()
    const { onOpen } = renderPage()
    fireEvent.click(within(card('Embedder')).getByRole('button', { name: 'Gerar embeddings' }))
    expect(b.enqueueJob).toHaveBeenCalledTimes(1)
    expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'embed', projectId: 'emb' })
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('"Atualizar agora" e "Instalar hooks" enfileiram pelo tipo e id', () => {
    const b = installBridge()
    renderPage()
    fireEvent.click(within(card('São Paulo')).getByRole('button', { name: 'Atualizar agora' }))
    fireEvent.click(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks' }))
    expect(b.enqueueJob).toHaveBeenNthCalledWith(1, { kind: 'update', projectId: 'stale' })
    expect(b.enqueueJob).toHaveBeenNthCalledWith(2, { kind: 'hooks-install', projectId: 'nohooks' })
  })

  it('"Abrir" chama onOpen uma vez só; clicar no card ou no nome também abre', () => {
    const b = installBridge()
    const { onOpen } = renderPage()
    fireEvent.click(within(card('Juriflux')).getByRole('button', { name: 'Abrir' }))
    expect(onOpen).toHaveBeenCalledTimes(1)
    expect(onOpen).toHaveBeenLastCalledWith('ok')

    fireEvent.click(within(card('São Paulo')).getByText('clientes'))
    expect(onOpen).toHaveBeenCalledTimes(2)
    expect(onOpen).toHaveBeenLastCalledWith('stale')

    fireEvent.click(within(card('Quebrado')).getByRole('button', { name: 'Quebrado' }))
    expect(onOpen).toHaveBeenCalledTimes(3)
    expect(onOpen).toHaveBeenLastCalledWith('err')

    // "Ver detalhes" abre, não enfileira.
    fireEvent.click(within(card('Sumido')).getByRole('button', { name: 'Ver detalhes' }))
    expect(onOpen).toHaveBeenCalledTimes(4)
    expect(onOpen).toHaveBeenLastCalledWith('gone')
    expect(b.enqueueJob).not.toHaveBeenCalled()
  })

  it('o botão desabilitado de um projeto indexando não abre o detalhe', () => {
    installBridge()
    const { onOpen } = renderPage()
    fireEvent.click(within(card('Ocupado')).getByRole('button', { name: 'Indexando…' }))
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('filtro segmentado: contadores batem e "Defasados" deixa só defasado e embeddings', () => {
    installBridge()
    renderPage()
    const group = screen.getByRole('radiogroup', { name: 'Filtrar projetos' })
    const all = within(group).getByRole('radio', { name: 'Todos (7)' })
    const outdated = within(group).getByRole('radio', { name: 'Defasados (2)' })
    const problem = within(group).getByRole('radio', { name: 'Com problema (2)' })
    expect(all).toHaveAttribute('aria-checked', 'true')
    expect(outdated).toHaveAttribute('aria-checked', 'false')
    expect(screen.getAllByRole('article')).toHaveLength(7)

    fireEvent.click(outdated)
    expect(outdated).toHaveAttribute('aria-checked', 'true')
    expect(all).toHaveAttribute('aria-checked', 'false')
    expect(screen.getAllByRole('article')).toHaveLength(2)
    expect(card('São Paulo')).toBeInTheDocument()
    expect(card('Embedder')).toBeInTheDocument()

    fireEvent.click(problem)
    expect(screen.getAllByRole('article')).toHaveLength(2)
    expect(card('Quebrado')).toBeInTheDocument()
    expect(card('Sumido')).toBeInTheDocument()
  })

  it('o filtro segmentado anda com as setas, como um grupo de rádio', () => {
    installBridge()
    renderPage()
    const all = screen.getByRole('radio', { name: 'Todos (7)' })
    expect(all).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('radio', { name: 'Defasados (2)' })).toHaveAttribute('tabindex', '-1')
    fireEvent.keyDown(all, { key: 'ArrowRight' })
    const outdated = screen.getByRole('radio', { name: 'Defasados (2)' })
    expect(outdated).toHaveAttribute('aria-checked', 'true')
    expect(outdated).toHaveFocus()
    fireEvent.keyDown(outdated, { key: 'ArrowLeft' })
    fireEvent.keyDown(screen.getByRole('radio', { name: 'Todos (7)' }), { key: 'ArrowLeft' })
    expect(screen.getByRole('radio', { name: 'Com problema (2)' })).toHaveAttribute('aria-checked', 'true')
  })

  it('filtro sem nenhum projeto avisa', () => {
    installBridge()
    renderPage({ projects: [ALL[0]], jobs: [] })
    fireEvent.click(screen.getByRole('radio', { name: 'Com problema (0)' }))
    expect(screen.getByText('Nenhum projeto neste filtro.')).toBeInTheDocument()
    expect(screen.queryAllByRole('article')).toHaveLength(0)
  })

  it('busca por nome ou pasta, sem diferenciar maiúsculas e acentos', () => {
    installBridge()
    const { rerender } = renderPage({ query: 'juri' })
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(card('Juriflux')).toBeInTheDocument()

    rerender(<ProjectsPage projects={ALL} jobs={BUSY} query="sao" onOpen={vi.fn()} />)
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(card('São Paulo')).toBeInTheDocument()

    rerender(<ProjectsPage projects={ALL} jobs={BUSY} query="  CLIENTES " onOpen={vi.fn()} />)
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(card('São Paulo')).toBeInTheDocument()
    // Os contadores acompanham a busca.
    expect(screen.getByRole('radio', { name: 'Todos (1)' })).toBeInTheDocument()
  })

  it('avisa quando o índice é de outra branch', () => {
    installBridge()
    renderPage({
      projects: [snap({ id: 'x', name: 'Branchy', git: { branch: 'feat/x', commit: 'c1' } })],
      jobs: [],
    })
    const c = within(card('Branchy'))
    expect(c.getByText('feat/x')).toBeInTheDocument()
    expect(c.getByText('índice da branch main')).toBeInTheDocument()
  })

  it('sem aviso de branch quando o índice é da branch atual', () => {
    installBridge()
    renderPage({ projects: [ALL[0]], jobs: [] })
    expect(within(card('Juriflux')).getByText('main')).toBeInTheDocument()
    expect(within(card('Juriflux')).queryByText(/índice da branch/)).not.toBeInTheDocument()
  })

  it('mostra há quanto tempo indexou, ou que ainda não indexou com esta versão', () => {
    installBridge()
    renderPage({ projects: [ALL[0], snap({ id: 'new', name: 'Novo', index: null })], jobs: [] })
    expect(within(card('Juriflux')).getByText('Indexado há 2 h')).toBeInTheDocument()
    expect(within(card('Novo')).getByText('Ainda não indexado com esta versão')).toBeInTheDocument()
  })

  it('cobertura de embeddings com legenda, em âmbar quando faltam', () => {
    installBridge()
    renderPage()
    const ok = within(card('Juriflux')).getByText('10 de 10 chunks com embedding')
    const missing = within(card('Embedder')).getByText('4 de 10 chunks com embedding')
    expect(ok).not.toHaveClass('is-warning')
    expect(missing).toHaveClass('is-warning')
    expect(within(card('Embedder')).getByRole('meter', { name: 'Cobertura de embeddings' })).toHaveAttribute(
      'aria-valuenow',
      '4',
    )
  })

  it('projeto indexando com tarefa rodando mostra progresso e previsão', () => {
    installBridge()
    renderPage()
    const c = within(card('Ocupado'))
    expect(c.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')
    expect(c.getByText('Faltam cerca de 2 min')).toBeInTheDocument()
  })

  it('projeto só na fila (sem tarefa rodando) não mostra barra de progresso', () => {
    installBridge()
    renderPage({ jobs: [job({ projectId: 'busy', state: 'queued', total: null, etaSeconds: null })] })
    expect(within(card('Ocupado')).getByRole('button', { name: 'Indexando…' })).toBeDisabled()
    expect(within(card('Ocupado')).queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('mostra a pasta relativa à pasta comum dos projetos', () => {
    installBridge()
    renderPage()
    expect(within(card('Juriflux')).getByText('aivon')).toBeInTheDocument()
    expect(within(card('São Paulo')).getByText('clientes')).toBeInTheDocument()
  })

  it('o card "Adicionar projeto" vem primeiro e abre o diálogo', () => {
    installBridge()
    renderPage()
    const add = screen.getByRole('button', { name: /^Adicionar projeto/ })
    expect(add).toHaveTextContent('Escolha uma pasta; o RAGX encontra os projetos dentro dela')
    const grid = screen.getByRole('list', { name: 'Projetos' })
    expect(within(grid).getAllByRole('listitem')[0]).toContainElement(add)
    fireEvent.click(add)
    expect(screen.getByRole('dialog', { name: 'Adicionar projeto' })).toBeInTheDocument()
  })

  describe('feedback de fila', () => {
    const HOOKS = (over: Partial<JobView> = {}) =>
      job({ id: 'jh', projectId: 'nohooks', kind: 'hooks-install', state: 'queued', ...over })

    it('com "hooks-install" na fila, o botão fica desabilitado e diz "Na fila"', () => {
      installBridge()
      renderPage({ jobs: [HOOKS()] })
      const c = within(card('Nohooks'))
      expect(c.getByRole('button', { name: 'Instalar hooks: na fila' })).toBeDisabled()
      expect(c.getByRole('button', { name: 'Instalar hooks: na fila' })).toHaveTextContent('Na fila')
      // Não é indexação: o selo continua o mesmo.
      expect(c.getByText('Sem hooks', { selector: '.badge-text' })).toBeInTheDocument()
    })

    it('com "hooks-install" rodando, o botão diz "Rodando"', () => {
      installBridge()
      renderPage({ jobs: [HOOKS({ state: 'running', total: null })] })
      expect(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks: rodando' })).toHaveTextContent(
        'Rodando',
      )
    })

    it('tarefa de outro projeto ou de outro tipo não desabilita o botão', () => {
      installBridge()
      renderPage({
        jobs: [HOOKS({ projectId: 'stale' }), HOOKS({ id: 'jg', kind: 'graph' })],
      })
      expect(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks' })).toBeEnabled()
    })

    it('clicar numa ação avisa que entrou na fila e o aviso some em 4 s', async () => {
      vi.useRealTimers()
      vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
      installBridge()
      renderPage()
      await act(async () => {
        fireEvent.click(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks' }))
      })
      const status = screen.getByRole('status')
      expect(status).toHaveAttribute('aria-live', 'polite')
      expect(status).toHaveTextContent('Adicionado à fila: Instalar hooks em Nohooks')
      act(() => {
        vi.advanceTimersByTime(3900)
      })
      expect(screen.getByText('Adicionado à fila: Instalar hooks em Nohooks')).toBeInTheDocument()
      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(screen.queryByText(/Adicionado à fila/)).not.toBeInTheDocument()
    })

    it('enqueueJob rejeitando mostra o erro e ele só some em 8 s', async () => {
      vi.useRealTimers()
      vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
      installBridge({ enqueueJob: vi.fn().mockRejectedValue(new Error('fila cheia')) })
      vi.spyOn(console, 'error').mockImplementation(() => {})
      renderPage()
      await act(async () => {
        fireEvent.click(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks' }))
      })
      expect(screen.getByText('Não foi possível adicionar à fila: fila cheia')).toBeInTheDocument()
      act(() => {
        vi.advanceTimersByTime(7900)
      })
      expect(screen.getByText('Não foi possível adicionar à fila: fila cheia')).toBeInTheDocument()
      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(screen.queryByText(/Não foi possível/)).not.toBeInTheDocument()
    })

    it('tarefa "failed" do projeto mostra "Última tarefa falhou:" com o erro', () => {
      installBridge()
      renderPage({ jobs: [HOOKS({ state: 'failed', error: 'não é um repositório git', finishedAt: '2026-09-23T11:00:00Z' })] })
      expect(within(card('Nohooks')).getByText('Última tarefa falhou: não é um repositório git')).toBeInTheDocument()
      // Botão volta a convidar ao clique.
      expect(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks' })).toBeEnabled()
      expect(within(card('Juriflux')).queryByText(/Última tarefa falhou/)).not.toBeInTheDocument()
    })

    it('uma nova tarefa ativa do projeto esconde o erro da anterior', () => {
      installBridge()
      renderPage({
        jobs: [
          HOOKS({ id: 'old', state: 'failed', error: 'boom', finishedAt: '2026-09-23T11:00:00Z' }),
          HOOKS({ id: 'new' }),
        ],
      })
      expect(within(card('Nohooks')).queryByText(/Última tarefa falhou/)).not.toBeInTheDocument()
    })

    it('desmontar limpa o timer do aviso', async () => {
      vi.useRealTimers()
      vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
      installBridge()
      const { unmount } = renderPage()
      await act(async () => {
        fireEvent.click(within(card('Nohooks')).getByRole('button', { name: 'Instalar hooks' }))
      })
      unmount()
      expect(vi.getTimerCount()).toBe(0)
    })
  })

  it('não quebra com projeto sem contagem, sem git e sem caminho', () => {
    installBridge()
    renderPage({
      projects: [snap({ id: 'bare', name: 'Cru', path: null, counts: null, git: null, index: null })],
      jobs: [],
    })
    const c = within(card('Cru'))
    expect(c.getByText('Com problema')).toBeInTheDocument()
    expect(c.getByText('Embeddings: sem dados')).toBeInTheDocument()
    expect(c.getByText('Sem git')).toBeInTheDocument()
  })
})

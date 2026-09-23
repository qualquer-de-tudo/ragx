import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ConnectionsPage } from '../ConnectionsPage'
import { useConnections } from '../../hooks/useConnections'
import { useJobs } from '../../hooks/useJobs'
import { connectionChecks, installBridge, job } from '../../test/snap'
import type { ConnectionCheck, JobView } from '../../types/ragx-bridge'

function renderPage(over: { connections?: ConnectionCheck[] | null; jobs?: JobView[]; checking?: boolean } = {}) {
  const onRefresh = vi.fn()
  const connections = over.connections === undefined ? connectionChecks() : over.connections
  const utils = render(
    <ConnectionsPage
      connections={connections}
      checking={over.checking ?? false}
      onRefresh={onRefresh}
      jobs={over.jobs ?? []}
    />,
  )
  return { ...utils, onRefresh }
}

const card = (name: string) => screen.getByRole('article', { name })

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-23T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ConnectionsPage', () => {
  it('título, frase e os três cards com o selo de cada estado', () => {
    installBridge()
    renderPage({ connections: connectionChecks({ ollama: { state: 'error', stateLabel: 'Não conectado' } }) })
    expect(screen.getByRole('heading', { level: 1, name: 'Conexões' })).toBeInTheDocument()
    expect(screen.getByText('O painel confere estas três peças a cada 30 segundos.')).toBeInTheDocument()

    expect(within(card('RAGX CLI')).getByText('Conectado')).toBeInTheDocument()
    expect(within(card('Claude Code')).getByText('Atenção')).toBeInTheDocument()
    expect(within(card('Ollama (Docker)')).getByText('Não conectado')).toBeInTheDocument()
  })

  it('mostra o resumo e os fatos (rótulo e valor) de cada card', () => {
    installBridge()
    renderPage()
    const ragx = card('RAGX CLI')
    expect(within(ragx).getByText('Respondendo normalmente.')).toBeInTheDocument()
    expect(within(ragx).getByText('Versão')).toBeInTheDocument()
    expect(within(ragx).getByText('ragx 0.9.0')).toBeInTheDocument()
    expect(within(card('Ollama (Docker)')).getByText('Projetos que dependem')).toBeInTheDocument()
    expect(within(card('Claude Code')).getByText('ragx')).toBeInTheDocument()
  })

  it('o card do Claude Code mostra a última chamada MCP, ou "nenhuma registrada"', () => {
    installBridge()
    const { unmount } = renderPage()
    const claude = card('Claude Code')
    expect(within(claude).getByText('Última chamada MCP')).toBeInTheDocument()
    expect(within(claude).getByText('há 5 min')).toBeInTheDocument()
    // Só no card do Claude Code.
    expect(within(card('RAGX CLI')).queryByText('Última chamada MCP')).not.toBeInTheDocument()
    unmount()

    renderPage({ connections: connectionChecks({ claude: { lastMcpCallAt: null } }) })
    expect(within(card('Claude Code')).getByText('nenhuma registrada')).toBeInTheDocument()
  })

  it('um botão por ação; "Baixar nomic-embed-text" enfileira o pull com o modelo', async () => {
    const b = installBridge()
    renderPage()
    fireEvent.click(within(card('Ollama (Docker)')).getByRole('button', { name: 'Baixar nomic-embed-text' }))
    await waitFor(() => expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'ollama-pull', model: 'nomic-embed-text' }))
  })

  it('"Registrar para todos os projetos" enfileira mcp-register sem modelo', async () => {
    const b = installBridge()
    renderPage()
    fireEvent.click(within(card('Claude Code')).getByRole('button', { name: 'Registrar para todos os projetos' }))
    await waitFor(() => expect(b.enqueueJob).toHaveBeenCalledTimes(1))
    expect(vi.mocked(b.enqueueJob).mock.calls[0][0]).toEqual({ kind: 'mcp-register' })
  })

  it('card sem ação não tem botão', () => {
    installBridge()
    renderPage()
    expect(within(card('RAGX CLI')).queryByRole('button')).not.toBeInTheDocument()
  })

  it('ação com tarefa do mesmo tipo rodando fica "Rodando" e desabilitada', () => {
    installBridge()
    renderPage({
      jobs: [job({ id: 'm', kind: 'mcp-register', label: 'Registrar o RAGX no Claude Code', projectId: null })],
    })
    const busy = within(card('Claude Code')).getByRole('button', { name: /Registrar para todos os projetos/ })
    expect(busy).toHaveTextContent('Rodando')
    expect(busy).toHaveAccessibleName('Registrar para todos os projetos: rodando')
    expect(busy).toBeDisabled()
  })

  it('na fila diz "Na fila"; o pull de outro modelo não trava este botão', () => {
    installBridge()
    const { unmount } = renderPage({
      jobs: [
        job({ id: 'q', kind: 'ollama-pull', model: 'nomic-embed-text', projectId: null, state: 'queued' }),
      ],
    })
    const queued = within(card('Ollama (Docker)')).getByRole('button', { name: /Baixar nomic-embed-text/ })
    expect(queued).toHaveTextContent('Na fila')
    expect(queued).toBeDisabled()
    unmount()

    renderPage({
      jobs: [job({ id: 'o', kind: 'ollama-pull', model: 'bge-m3', projectId: null })],
    })
    const free = within(card('Ollama (Docker)')).getByRole('button', { name: 'Baixar nomic-embed-text' })
    expect(free).toBeEnabled()
  })

  it('ajuda aparece em bloco mono que dá para copiar', async () => {
    installBridge()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const help = 'Crie com: docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama'
    renderPage({
      connections: connectionChecks({ ollama: { state: 'error', stateLabel: 'Não conectado', actions: [], help } }),
    })
    const ollama = card('Ollama (Docker)')
    expect(within(ollama).getByText(help).tagName).toBe('PRE')
    fireEvent.click(within(ollama).getByRole('button', { name: 'Copiar' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(help))
    expect(await within(ollama).findByText('Copiado')).toBeInTheDocument()
  })

  it('antes da primeira checagem mostra os três cards em "Verificando…", nada verde', () => {
    installBridge()
    renderPage({ connections: null, checking: true })
    for (const name of ['RAGX CLI', 'Claude Code', 'Ollama (Docker)']) {
      expect(within(card(name)).getByText('Verificando…')).toBeInTheDocument()
    }
    expect(screen.queryByText('Conectado')).not.toBeInTheDocument()
  })

  it('"Verificar agora" chama getConnections', async () => {
    const b = installBridge({ getConnections: vi.fn().mockResolvedValue(connectionChecks()) })
    function Harness() {
      const { connections, checking, refresh } = useConnections()
      const jobs = useJobs()
      return <ConnectionsPage connections={connections} checking={checking} onRefresh={() => void refresh()} jobs={jobs} />
    }
    render(<Harness />)
    const button = await screen.findByRole('button', { name: 'Verificar agora' })
    expect(b.getConnections).toHaveBeenCalledTimes(1)
    fireEvent.click(button)
    await waitFor(() => expect(b.getConnections).toHaveBeenCalledTimes(2))
  })

  it('checagem em andamento: o botão diz "Verificando…" e fica desabilitado', () => {
    installBridge()
    renderPage({ checking: true })
    expect(screen.getByRole('button', { name: 'Verificando…' })).toBeDisabled()
  })
})

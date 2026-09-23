import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ConnectionsPage } from '../ConnectionsPage'
import { useConnections } from '../../hooks/useConnections'
import { useJobs } from '../../hooks/useJobs'
import { connectionChecks, installBridge, job } from '../../test/snap'
import type { ConnectionCheck, JobView, OllamaBenchmark } from '../../types/ragx-bridge'

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
    for (const name of ['RAGX CLI', 'Claude Code', 'Ollama']) {
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

  it('antes da primeira checagem o card do Ollama não diz em que modo roda', () => {
    installBridge()
    renderPage({ connections: null, checking: true })
    expect(within(card('Ollama')).getByText('Verificando…')).toBeInTheDocument()
    expect(screen.queryByText('Ollama (Docker)')).not.toBeInTheDocument()
  })
})

/** Ollama no Docker, na CPU, com a troca recomendada e as duas ações de apoio. */
const OLLAMA_DOCKER: Partial<ConnectionCheck> = {
  title: 'Ollama (Docker)',
  state: 'ok',
  stateLabel: 'Conectado',
  summary: 'Rodando no Docker, com os modelos que os projetos usam.',
  facts: [
    { label: 'Modo', value: 'Docker' },
    { label: 'Processador', value: 'CPU' },
    { label: 'Velocidade', value: '3,2 chunks/s' },
    { label: 'Modelos instalados', value: 'nomic-embed-text:latest' },
    { label: 'Projetos que dependem', value: '1 projeto(s): Juriflux' },
  ],
  actions: [
    { kind: 'ollama-use-native', label: 'Trocar para o Ollama local (usa sua GPU)' },
    { kind: 'ollama-benchmark', label: 'Medir velocidade', secondary: true },
    { kind: 'ollama-stop', label: 'Parar o Ollama', secondary: true },
  ],
  help: 'Sua placa é AMD: o Ollama local usa a GPU; no Docker ele fica na CPU.',
}

const ollamaCard = () => card('Ollama (Docker)')
const button = (name: string | RegExp) => within(ollamaCard()).getByRole('button', { name })

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const BENCH_OK: OllamaBenchmark = {
  ok: true,
  chunksPerSecond: 3.2,
  processor: 'cpu',
  vramMB: null,
  model: 'nomic-embed-text',
  measuredAt: '2026-09-23T12:00:00Z',
  error: null,
}

describe('ConnectionsPage: card do Ollama', () => {
  it('ação principal em destaque; as de apoio neutras, num grupo abaixo', () => {
    installBridge()
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    const primary = button('Trocar para o Ollama local (usa sua GPU)')
    expect(primary).toHaveClass('btn-primary')

    const group = within(ollamaCard()).getByRole('group', { name: 'Outras ações' })
    for (const name of ['Medir velocidade', 'Parar o Ollama']) {
      const secondary = within(group).getByRole('button', { name })
      expect(secondary).toHaveClass('btn')
      expect(secondary).not.toHaveClass('btn-primary')
    }
    // O grupo de apoio vem depois das principais.
    expect(primary.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(group).queryByRole('button', { name: /Trocar/ })).not.toBeInTheDocument()
  })

  it('mostra modo, processador e velocidade como fatos', () => {
    installBridge()
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    for (const text of ['Modo', 'Docker', 'Processador', 'CPU', 'Velocidade', '3,2 chunks/s']) {
      expect(within(ollamaCard()).getByText(text)).toBeInTheDocument()
    }
  })

  it('"Trocar para o Ollama local" enfileira ollama-use-native sem mais nada', async () => {
    const b = installBridge()
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    fireEvent.click(button('Trocar para o Ollama local (usa sua GPU)'))
    await waitFor(() => expect(b.enqueueJob).toHaveBeenCalledTimes(1))
    expect(vi.mocked(b.enqueueJob).mock.calls[0][0]).toEqual({ kind: 'ollama-use-native' })
  })

  it('"Parar o Ollama" enfileira ollama-stop', async () => {
    const b = installBridge()
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    fireEvent.click(button('Parar o Ollama'))
    await waitFor(() => expect(b.enqueueJob).toHaveBeenCalledTimes(1))
    expect(vi.mocked(b.enqueueJob).mock.calls[0][0]).toEqual({ kind: 'ollama-stop' })
  })

  it('"Medir velocidade" roda o benchmark, fica "Medindo…" e depois pede a checagem nova', async () => {
    const bench = deferred<OllamaBenchmark>()
    const b = installBridge({ runOllamaBenchmark: vi.fn(() => bench.promise) })
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    fireEvent.click(button('Medir velocidade'))

    const measuring = button('Medir velocidade: medindo')
    expect(measuring).toHaveTextContent('Medindo…')
    expect(measuring).toBeDisabled()
    expect(measuring).toHaveAttribute('aria-busy', 'true')
    expect(b.runOllamaBenchmark).toHaveBeenCalledTimes(1)
    expect(b.runOllamaBenchmark).toHaveBeenCalledWith()
    expect(b.getConnections).not.toHaveBeenCalled()
    expect(b.enqueueJob).not.toHaveBeenCalled()
    // Um segundo clique não dispara outra medição.
    fireEvent.click(measuring)
    expect(b.runOllamaBenchmark).toHaveBeenCalledTimes(1)

    bench.resolve(BENCH_OK)
    await waitFor(() => expect(b.getConnections).toHaveBeenCalledTimes(1))
    const again = await within(ollamaCard()).findByRole('button', { name: 'Medir velocidade' })
    expect(again).toBeEnabled()
    expect(again).not.toHaveAttribute('aria-busy')
    expect(within(ollamaCard()).queryByText(/Não foi possível medir/)).not.toBeInTheDocument()
  })

  it('benchmark que volta com erro mostra "Não foi possível medir: …" no card', async () => {
    const b = installBridge({
      runOllamaBenchmark: vi.fn().mockResolvedValue({
        ...BENCH_OK,
        ok: false,
        chunksPerSecond: null,
        processor: 'unknown',
        error: 'O modelo nomic-embed-text não está instalado.',
      }),
    })
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    fireEvent.click(button('Medir velocidade'))
    const alert = await within(ollamaCard()).findByRole('alert')
    expect(alert).toHaveTextContent('Não foi possível medir: O modelo nomic-embed-text não está instalado.')
    await waitFor(() => expect(b.getConnections).toHaveBeenCalledTimes(1))
    expect(button('Medir velocidade')).toBeEnabled()
  })

  it('benchmark que falha (promessa rejeitada) mostra a mensagem da exceção; medir de novo limpa o erro', async () => {
    const run = vi
      .fn<() => Promise<OllamaBenchmark>>()
      .mockRejectedValueOnce(new Error('o processo principal não respondeu'))
      .mockResolvedValueOnce(BENCH_OK)
    installBridge({ runOllamaBenchmark: run })
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderPage({ connections: connectionChecks({ ollama: OLLAMA_DOCKER }) })
    fireEvent.click(button('Medir velocidade'))
    expect(await within(ollamaCard()).findByRole('alert')).toHaveTextContent(
      'Não foi possível medir: o processo principal não respondeu',
    )

    fireEvent.click(await within(ollamaCard()).findByRole('button', { name: 'Medir velocidade' }))
    await waitFor(() => expect(run).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(within(ollamaCard()).queryByRole('alert')).not.toBeInTheDocument())
    quiet.mockRestore()
  })

  it('troca em andamento: botão desabilitado com o estado e o aviso com o rótulo da tarefa', () => {
    installBridge()
    renderPage({
      connections: connectionChecks({ ollama: OLLAMA_DOCKER }),
      jobs: [job({ id: 's', kind: 'ollama-use-native', label: 'Usar o Ollama local', projectId: null })],
    })
    const busy = button(/Trocar para o Ollama local/)
    expect(busy).toHaveTextContent('Rodando')
    expect(busy).toHaveAccessibleName('Trocar para o Ollama local (usa sua GPU): rodando')
    expect(busy).toBeDisabled()

    const note = within(ollamaCard()).getByRole('status', { name: 'Troca do Ollama em andamento' })
    expect(within(note).getByText('Usar o Ollama local')).toBeInTheDocument()
    expect(within(note).getByText('A troca leva alguns minutos; acompanhe pela fila no topo.')).toBeInTheDocument()
    // As outras ações continuam livres.
    expect(button('Parar o Ollama')).toBeEnabled()
  })

  it('o aviso da troca aparece mesmo quando o card já não oferece o botão de trocar', () => {
    installBridge()
    renderPage({
      connections: connectionChecks({
        ollama: { title: 'Ollama', state: 'error', stateLabel: 'Não conectado', actions: [], help: null },
      }),
      jobs: [
        job({ id: 's', kind: 'ollama-use-docker', label: 'Usar o Ollama no Docker', projectId: null, state: 'queued' }),
      ],
    })
    const note = within(card('Ollama')).getByRole('status', { name: 'Troca do Ollama em andamento' })
    expect(within(note).getByText('Usar o Ollama no Docker')).toBeInTheDocument()
    // Só no card do Ollama.
    expect(within(card('Claude Code')).queryByRole('status', { name: 'Troca do Ollama em andamento' })).toBeNull()
  })

  it('sem troca em andamento não há aviso de troca', () => {
    installBridge()
    renderPage({
      connections: connectionChecks({ ollama: OLLAMA_DOCKER }),
      jobs: [job({ id: 'p', kind: 'ollama-stop', label: 'Parar o Ollama', projectId: null, state: 'queued' })],
    })
    expect(within(ollamaCard()).queryByText(/A troca leva alguns minutos/)).not.toBeInTheDocument()
    const stop = button(/Parar o Ollama/)
    expect(stop).toHaveTextContent('Na fila')
    expect(stop).toBeDisabled()
  })

  it('"Iniciar container" enfileira ollama-start e fica "Na fila" com a tarefa na fila', async () => {
    const b = installBridge()
    const down: Partial<ConnectionCheck> = {
      title: 'Ollama (Docker)',
      state: 'error',
      stateLabel: 'Não conectado',
      facts: [
        { label: 'Modelos instalados', value: 'sem dados' },
        { label: 'Projetos que dependem', value: '1 projeto(s): Juriflux' },
      ],
      actions: [{ kind: 'ollama-start', label: 'Iniciar container' }],
    }
    const { unmount } = renderPage({ connections: connectionChecks({ ollama: down }) })
    expect(within(ollamaCard()).getByText('sem dados')).toBeInTheDocument()
    fireEvent.click(button('Iniciar container'))
    await waitFor(() => expect(b.enqueueJob).toHaveBeenCalledTimes(1))
    expect(vi.mocked(b.enqueueJob).mock.calls[0][0]).toEqual({ kind: 'ollama-start' })
    unmount()

    renderPage({
      connections: connectionChecks({ ollama: down }),
      jobs: [job({ id: 'st', kind: 'ollama-start', label: 'Iniciar o Ollama', projectId: null, state: 'queued' })],
    })
    expect(button(/Iniciar container/)).toHaveTextContent('Na fila')
    expect(button(/Iniciar container/)).toBeDisabled()
  })
})

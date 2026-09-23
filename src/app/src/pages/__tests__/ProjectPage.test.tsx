import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ProjectPage } from '../ProjectPage'
import { installBridge, job, snap } from '../../test/snap'
import type { JobView, ProjectSnapshot, RagxBridge } from '../../types/ragx-bridge'

/** Resposta de `ragx status --json`; cada teste troca só o que importa. */
function status(over: Record<string, unknown> = {}) {
  return {
    initialized: true,
    documents: 3,
    chunks: 10,
    embeddings: 10,
    freshness: { state: 'fresh', current: { branch: 'main', commit: 'c1', dirty: false }, reasons: [] },
    recent_runs: [],
    ...over,
  }
}

function stale(reasons: unknown[]) {
  return status({ freshness: { state: 'stale', current: { branch: 'feat/x', commit: 'c2', dirty: true }, reasons } })
}

function run(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    started_at: '2026-09-23T11:59:00Z',
    finished_at: '2026-09-23T11:59:30Z',
    mode: 'incremental',
    source: 'cli',
    git_branch: 'main',
    git_commit: 'abc1234def5678',
    git_dirty: 0,
    indexed: 0,
    error: null,
    ...over,
  }
}

function renderPage(
  over: {
    project?: ProjectSnapshot | null
    jobs?: JobView[]
    status?: unknown
    bridge?: Partial<RagxBridge>
  } = {},
) {
  const b = installBridge({
    getProjectStatus: vi.fn().mockResolvedValue('status' in over ? over.status : status()),
    ...over.bridge,
  })
  const onBack = vi.fn()
  const project = over.project === undefined ? snap() : over.project
  const utils = render(<ProjectPage project={project} jobs={over.jobs ?? []} onBack={onBack} />)
  return { ...utils, onBack, bridge: b }
}

const section = (name: string) => screen.getByRole('region', { name })

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-23T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ProjectPage: topo', () => {
  it('mostra nome, selo, caminho completo e branch atual; voltar chama onBack', async () => {
    const { onBack } = renderPage({
      project: snap({ name: 'Juriflux', path: 'C:/projects/aivon/juriflux', git: { branch: 'feat/x', commit: 'c1' } }),
    })
    expect(screen.getByRole('heading', { level: 1, name: 'Juriflux' })).toBeInTheDocument()
    expect(screen.getByText('C:/projects/aivon/juriflux')).toBeInTheDocument()
    expect(screen.getByText('feat/x')).toBeInTheDocument()
    expect(screen.getByText('Defasado').closest('.badge')).toHaveTextContent('● Defasado')
    fireEvent.click(screen.getByRole('button', { name: 'Voltar para Projetos' }))
    expect(onBack).toHaveBeenCalledTimes(1)
    await screen.findByText('Em dia com o que está no disco')
  })

  it('tarefa que não indexa (dicionário) não deixa o selo "Indexando…"; embed deixa', async () => {
    const { rerender, onBack } = renderPage({ jobs: [job({ kind: 'dictionary', state: 'running' })] })
    expect(screen.getByText('Atualizado').closest('.badge')).toHaveTextContent('● Atualizado')
    expect(screen.queryByText('Indexando…')).not.toBeInTheDocument()
    rerender(<ProjectPage project={snap()} jobs={[job({ kind: 'embed', state: 'running' })]} onBack={onBack} />)
    expect(screen.getByText('Indexando…').closest('.badge')).toHaveTextContent('● Indexando…')
    await screen.findByText('Em dia com o que está no disco')
  })

  it('projeto que sumiu do hub: avisa e deixa voltar', () => {
    const { onBack, bridge } = renderPage({ project: null })
    expect(screen.getByRole('heading', { level: 1, name: 'Projeto não encontrado' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Voltar para Projetos' }))
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(bridge.getProjectStatus).not.toHaveBeenCalled()
  })
})

describe('ProjectPage: índice', () => {
  it('quatro números: documentos, chunks, embeddings e cobertura', async () => {
    renderPage({ project: snap({ counts: { documents: 1234, chunks: 200, embeddings: 150, pendingEmbeddings: 50 } }) })
    const idx = within(section('Índice'))
    expect(idx.getByText('Documentos').nextSibling).toHaveTextContent('1.234')
    expect(idx.getByText('Chunks').nextSibling).toHaveTextContent('200')
    expect(idx.getByText('Embeddings').nextSibling).toHaveTextContent('150')
    expect(idx.getByText('Cobertura').nextSibling).toHaveTextContent('75%')
    await screen.findByText('Em dia com o que está no disco')
  })

  it('avisa quando faltam embeddings e "Gerar embeddings" enfileira', async () => {
    const { bridge } = renderPage({
      project: snap({ counts: { documents: 10, chunks: 200, embeddings: 0, pendingEmbeddings: 200 } }),
    })
    const idx = within(section('Índice'))
    expect(
      idx.getByText('200 chunks sem embedding: a busca semântica cai para palavra-chave nesses trechos.'),
    ).toBeInTheDocument()
    fireEvent.click(idx.getByRole('button', { name: 'Gerar embeddings' }))
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'embed', projectId: 'p1' })
    await screen.findByText('Em dia com o que está no disco')
  })

  it('não avisa quando todos os chunks têm embedding', async () => {
    renderPage()
    expect(screen.queryByText(/sem embedding: a busca semântica/)).not.toBeInTheDocument()
    await screen.findByText('Em dia com o que está no disco')
  })

  it('sem contagens, explica por quê', () => {
    renderPage({
      project: snap({ exists: false, counts: null, countsUnavailableReason: 'pasta do projeto não existe mais' }),
    })
    expect(within(section('Índice')).getByText('pasta do projeto não existe mais')).toBeInTheDocument()
  })
})

describe('ProjectPage: está em dia?', () => {
  it('em dia: diz que está em dia com o disco', async () => {
    renderPage()
    expect(await within(section('Está em dia?')).findByText('Em dia com o que está no disco')).toBeInTheDocument()
  })

  it('enquanto verifica, diz "Verificando…"', () => {
    renderPage({ bridge: { getProjectStatus: vi.fn(() => new Promise(() => {})) } })
    expect(within(section('Está em dia?')).getByText('Verificando…')).toBeInTheDocument()
  })

  it('falha ao verificar mostra a mensagem real', async () => {
    renderPage({ bridge: { getProjectStatus: vi.fn().mockRejectedValue(new Error('ragx não encontrado no PATH')) } })
    expect(
      await screen.findByText('Não foi possível verificar agora: ragx não encontrado no PATH'),
    ).toBeInTheDocument()
  })

  it('branch trocada', async () => {
    renderPage({ status: stale([{ kind: 'branch_changed', indexed: 'main', current: 'feat/x' }]) })
    expect(await screen.findByText('O índice é da branch main; você está em feat/x.')).toBeInTheDocument()
  })

  it('commits depois da indexação, com e sem contagem', async () => {
    renderPage({ status: stale([{ kind: 'commits_since_index', count: 3 }]) })
    expect(await screen.findByText('3 commit(s) depois da última indexação.')).toBeInTheDocument()
  })

  it('commits depois da indexação sem contagem', async () => {
    renderPage({ status: stale([{ kind: 'commits_since_index', count: null }]) })
    expect(await screen.findByText('Há commits depois da última indexação.')).toBeInTheDocument()
  })

  it('arquivos alterados depois da indexação', async () => {
    renderPage({ status: stale([{ kind: 'uncommitted_changes', count: 2 }]) })
    expect(await screen.findByText('2 arquivo(s) alterado(s) depois da última indexação.')).toBeInTheDocument()
  })

  it('embeddings pendentes', async () => {
    renderPage({ status: stale([{ kind: 'pending_embeddings', count: 5 }]) })
    expect(await screen.findByText('5 chunk(s) sem embedding.')).toBeInTheDocument()
  })

  it('vários motivos aparecem juntos, na ordem, sem o "em dia"', async () => {
    renderPage({
      status: stale([
        { kind: 'branch_changed', indexed: 'main', current: 'feat/x' },
        { kind: 'uncommitted_changes', count: 1 },
      ]),
    })
    const items = await within(section('Está em dia?')).findAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual([
      'O índice é da branch main; você está em feat/x.',
      '1 arquivo(s) alterado(s) depois da última indexação.',
    ])
    expect(screen.queryByText('Em dia com o que está no disco')).not.toBeInTheDocument()
  })

  it('estado desconhecido explica por quê', async () => {
    renderPage({ status: status({ freshness: { state: 'unknown', current: null, reasons: [] } }) })
    expect(
      await screen.findByText(
        'Não dá para saber: o projeto não está num repositório git ou ainda não foi indexado com esta versão.',
      ),
    ).toBeInTheDocument()
  })

  it('projeto ainda não inicializado conta como desconhecido', async () => {
    renderPage({ status: { initialized: false } })
    expect(await screen.findByText(/^Não dá para saber:/)).toBeInTheDocument()
  })

  it('resposta em formato inesperado não quebra a página', async () => {
    renderPage({
      status: status({
        freshness: { state: 'stale', reasons: [{ kind: 'branch_changed' }, { kind: 'novo_motivo', count: 1 }, null] },
        recent_runs: [null, 'x', { id: 'r', started_at: 42 }],
      }),
    })
    expect(await screen.findByText('O índice está defasado.')).toBeInTheDocument()
    expect(within(section('Linha do tempo')).getAllByRole('listitem')).toHaveLength(1)
  })

  it('resposta que nem é objeto vira mensagem de erro', async () => {
    renderPage({ status: 'oops' })
    expect(
      await screen.findByText('Não foi possível verificar agora: resposta inesperada do ragx status'),
    ).toBeInTheDocument()
  })

  it('pasta ausente: nem chama o ragx status', () => {
    const { bridge } = renderPage({
      project: snap({ exists: false, counts: null, countsUnavailableReason: 'pasta do projeto não existe mais' }),
    })
    expect(bridge.getProjectStatus).not.toHaveBeenCalled()
    expect(
      within(section('Está em dia?')).getByText('Não foi possível verificar agora: pasta do projeto não existe mais'),
    ).toBeInTheDocument()
  })

  it('resposta atrasada do projeto anterior não aparece no projeto novo', async () => {
    let resolveA: (v: unknown) => void = () => {}
    const getProjectStatus = vi.fn((id: string) =>
      id === 'a'
        ? new Promise((resolve) => {
            resolveA = resolve
          })
        : Promise.resolve(status()),
    )
    const { rerender, onBack } = renderPage({ project: snap({ id: 'a', name: 'A' }), bridge: { getProjectStatus } })
    expect(within(section('Está em dia?')).getByText('Verificando…')).toBeInTheDocument()

    // Mesmo componente (sem `key`): o caso mais difícil para a guarda.
    rerender(<ProjectPage project={snap({ id: 'b', name: 'B' })} jobs={[]} onBack={onBack} />)
    expect(await screen.findByText('Em dia com o que está no disco')).toBeInTheDocument()

    resolveA(stale([{ kind: 'branch_changed', indexed: 'main', current: 'feat/a' }]))
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByText('O índice é da branch main; você está em feat/a.')).not.toBeInTheDocument()
    expect(screen.getByText('Em dia com o que está no disco')).toBeInTheDocument()
    expect(getProjectStatus.mock.calls.map((c) => c[0])).toEqual(['a', 'b'])
  })

  it('verifica de novo quando o snapshot traz uma indexação nova', async () => {
    const { bridge, rerender, onBack } = renderPage()
    await screen.findByText('Em dia com o que está no disco')
    expect(bridge.getProjectStatus).toHaveBeenCalledTimes(1)
    rerender(
      <ProjectPage
        project={snap({ index: { finishedAt: '2026-09-23T11:59:59Z', mode: 'incremental', source: 'hook:post-commit', branch: 'main', commit: 'c1' } })}
        jobs={[]}
        onBack={onBack}
      />,
    )
    await waitFor(() => expect(bridge.getProjectStatus).toHaveBeenCalledTimes(2))
    expect(bridge.getProjectStatus).toHaveBeenLastCalledWith('p1')
  })
})

describe('ProjectPage: linha do tempo', () => {
  it('traduz origem e modo, e mostra quando, branch, commit e o que mudou', async () => {
    renderPage({
      status: status({
        recent_runs: [
          run({ id: 3, source: 'hook:post-checkout', mode: 'incremental', git_branch: 'feat/x', indexed: 12 }),
          run({ id: 2, source: 'mcp:refresh', mode: 'embed-only', finished_at: '2026-09-23T10:00:00Z' }),
          run({ id: 1, source: 'panel', mode: 'full', finished_at: null, started_at: '2026-09-21T12:00:00Z', error: 'Ollama fora do ar' }),
        ],
      }),
    })
    const tl = within(section('Linha do tempo'))
    const items = await tl.findAllByRole('listitem')
    expect(items).toHaveLength(3)

    const first = within(items[0])
    expect(first.getByText('agora')).toBeInTheDocument()
    expect(first.getByText('Troca de branch')).toBeInTheDocument()
    expect(first.getByText('incremental')).toBeInTheDocument()
    expect(first.getByText('feat/x')).toBeInTheDocument()
    expect(first.getByText('abc1234')).toBeInTheDocument()
    expect(first.getByText('12 arquivo(s) reindexado(s)')).toBeInTheDocument()

    const second = within(items[1])
    expect(second.getByText('há 2 h')).toBeInTheDocument()
    expect(second.getByText('Agente (refresh)')).toBeInTheDocument()
    expect(second.getByText('só embeddings')).toBeInTheDocument()
    expect(second.getByText('sem mudanças')).toBeInTheDocument()

    const third = within(items[2])
    expect(third.getByText('há 2 dias')).toBeInTheDocument()
    expect(third.getByText('Painel')).toBeInTheDocument()
    expect(third.getByText('completa')).toBeInTheDocument()
    expect(third.getByText('Ollama fora do ar')).toHaveClass('is-critical')
  })

  it.each([
    ['cli', 'Terminal'],
    ['watch', 'Watcher'],
    ['sync', 'Sync'],
    ['mcp:index', 'Agente (reindex)'],
    ['hook:post-commit', 'Commit'],
    ['hook:post-merge', 'Merge ou pull'],
  ])('origem %s aparece como "%s"', async (source, label) => {
    renderPage({ status: status({ recent_runs: [run({ source })] }) })
    expect(await within(section('Linha do tempo')).findByText(label)).toBeInTheDocument()
  })

  it('mostra só as 10 mais recentes', async () => {
    renderPage({ status: status({ recent_runs: Array.from({ length: 12 }, (_, i) => run({ id: i + 1 })) }) })
    await screen.findAllByText('Terminal')
    expect(within(section('Linha do tempo')).getAllByRole('listitem')).toHaveLength(10)
  })

  it('sem indexações registradas, diz isso', async () => {
    renderPage()
    expect(await screen.findByText('Nenhuma indexação registrada ainda.')).toBeInTheDocument()
  })
})

describe('ProjectPage: hooks de git', () => {
  it('instalados: interruptor ligado, e desligar enfileira hooks-uninstall', async () => {
    const { bridge } = renderPage({ project: snap({ hooksInstalled: true }) })
    const hooks = within(section('Hooks de git'))
    expect(
      hooks.getByText('Instalados: o índice se atualiza ao trocar de branch, commitar e fazer merge.'),
    ).toBeInTheDocument()
    const sw = hooks.getByRole('switch', { name: 'Hooks de git' })
    expect(sw).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(sw)
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'hooks-uninstall', projectId: 'p1' })
    await screen.findByText('Em dia com o que está no disco')
  })

  it('não instalados: interruptor desligado, e ligar enfileira hooks-install', async () => {
    const { bridge } = renderPage({ project: snap({ hooksInstalled: false }) })
    const hooks = within(section('Hooks de git'))
    expect(hooks.getByText('Não instalados.')).toBeInTheDocument()
    const sw = hooks.getByRole('switch', { name: 'Hooks de git' })
    expect(sw).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(sw)
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'hooks-install', projectId: 'p1' })
    await screen.findByText('Em dia com o que está no disco')
  })

  it('fora de repositório git: explica e desabilita o interruptor', async () => {
    renderPage({ project: snap({ git: null, hooksInstalled: null }) })
    const hooks = within(section('Hooks de git'))
    expect(hooks.getByText('Este projeto não está num repositório git.')).toBeInTheDocument()
    expect(hooks.getByRole('switch', { name: 'Hooks de git' })).toBeDisabled()
    await screen.findByText('Em dia com o que está no disco')
  })

  it('com tarefa de hooks na fila, o interruptor espera', async () => {
    renderPage({ jobs: [job({ kind: 'hooks-install', state: 'queued' })], project: snap({ hooksInstalled: false }) })
    const hooks = within(section('Hooks de git'))
    expect(hooks.getByRole('switch', { name: 'Hooks de git' })).toBeDisabled()
    expect(hooks.getByText('Na fila')).toBeInTheDocument()
    await screen.findByText('Em dia com o que está no disco')
  })
})

describe('ProjectPage: manutenção e knowledge', () => {
  it('"Atualizar agora" enfileira update', async () => {
    const { bridge } = renderPage()
    fireEvent.click(within(section('Manutenção')).getByRole('button', { name: 'Atualizar agora' }))
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'update', projectId: 'p1' })
    await screen.findByText('Em dia com o que está no disco')
  })

  it('"Gerar embeddings faltantes" fica desabilitado sem pendentes e enfileira embed com pendentes', async () => {
    const { bridge, rerender, onBack } = renderPage()
    expect(within(section('Manutenção')).getByRole('button', { name: 'Gerar embeddings faltantes' })).toBeDisabled()
    rerender(
      <ProjectPage
        project={snap({ counts: { documents: 3, chunks: 10, embeddings: 4, pendingEmbeddings: 6 } })}
        jobs={[]}
        onBack={onBack}
      />,
    )
    const button = within(section('Manutenção')).getByRole('button', { name: 'Gerar embeddings faltantes' })
    expect(button).toBeEnabled()
    fireEvent.click(button)
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'embed', projectId: 'p1' })
    await screen.findByText(/sem embedding/)
  })

  it('"Reindexar do zero" só enfileira no segundo clique', async () => {
    const { bridge } = renderPage()
    const m = within(section('Manutenção'))
    expect(
      m.getByText('Descarta o cache e lê todos os arquivos de novo. Use quando algo parecer errado no índice.'),
    ).toBeInTheDocument()
    fireEvent.click(m.getByRole('button', { name: 'Reindexar do zero' }))
    expect(bridge.enqueueJob).not.toHaveBeenCalled()
    fireEvent.click(m.getByRole('button', { name: 'Confirmar reindexação' }))
    expect(bridge.enqueueJob).toHaveBeenCalledTimes(1)
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'reindex-full', projectId: 'p1' })
    await screen.findByText('Em dia com o que está no disco')
  })

  it('ação com tarefa ativa do mesmo tipo fica desabilitada com "Na fila" ou "Rodando"', async () => {
    renderPage({
      jobs: [
        job({ id: 'a', kind: 'update', state: 'queued' }),
        job({ id: 'b', kind: 'reindex-full', state: 'running' }),
        job({ id: 'c', kind: 'graph', state: 'running' }),
        // Outro projeto e tarefa já terminada não contam.
        job({ id: 'd', kind: 'sync', state: 'running', projectId: 'outro' }),
        job({ id: 'e', kind: 'dictionary', state: 'done' }),
      ],
    })
    const m = within(section('Manutenção'))
    const update = m.getByRole('button', { name: 'Atualizar agora: na fila' })
    expect(update).toBeDisabled()
    expect(update).toHaveTextContent('Na fila')
    const full = m.getByRole('button', { name: 'Reindexar do zero: rodando' })
    expect(full).toBeDisabled()
    expect(full).toHaveTextContent('Rodando')

    const k = within(section('Knowledge versionado'))
    expect(k.getByRole('button', { name: 'Reconstruir grafo: rodando' })).toBeDisabled()
    expect(k.getByRole('button', { name: 'Sincronizar knowledge' })).toBeEnabled()
    expect(k.getByRole('button', { name: 'Gerar dicionário' })).toBeEnabled()
    await screen.findByText('Em dia com o que está no disco')
  })

  it('knowledge avisa do diff e enfileira sync, graph e dictionary', async () => {
    const { bridge } = renderPage()
    const k = within(section('Knowledge versionado'))
    expect(
      k.getByText('Estas ações alteram arquivos versionados em knowledge/. Revise o diff antes de commitar.'),
    ).toBeInTheDocument()
    fireEvent.click(k.getByRole('button', { name: 'Sincronizar knowledge' }))
    fireEvent.click(k.getByRole('button', { name: 'Reconstruir grafo' }))
    fireEvent.click(k.getByRole('button', { name: 'Gerar dicionário' }))
    expect(bridge.enqueueJob).toHaveBeenNthCalledWith(1, { kind: 'sync', projectId: 'p1' })
    expect(bridge.enqueueJob).toHaveBeenNthCalledWith(2, { kind: 'graph', projectId: 'p1' })
    expect(bridge.enqueueJob).toHaveBeenNthCalledWith(3, { kind: 'dictionary', projectId: 'p1' })
    await screen.findByText('Em dia com o que está no disco')
  })
})

describe('ProjectPage: remover do hub', () => {
  it('só enfileira no segundo clique e depois volta para Projetos', async () => {
    const { bridge, onBack } = renderPage()
    expect(screen.getByText('Tira o projeto do painel. Nada é apagado no disco.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remover do hub' }))
    expect(bridge.enqueueJob).not.toHaveBeenCalled()
    expect(onBack).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar remoção' }))
    expect(bridge.enqueueJob).toHaveBeenCalledWith({ kind: 'remove-from-hub', projectId: 'p1' })
    await waitFor(() => expect(onBack).toHaveBeenCalledTimes(1))
  })

  it('se não der para enfileirar, fica na página e diz por quê', async () => {
    const { onBack } = renderPage({
      bridge: { enqueueJob: vi.fn().mockRejectedValue(new Error('projeto desconhecido: p1')) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Remover do hub' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar remoção' }))
    expect(await screen.findByText('Não foi possível remover agora: projeto desconhecido: p1')).toBeInTheDocument()
    expect(onBack).not.toHaveBeenCalled()
  })
})

describe('ProjectPage: uso pelos agentes', () => {
  it('sem chamadas nas últimas 24 h, explica quando aparecem', async () => {
    renderPage()
    expect(within(section('Uso pelos agentes nas últimas 24 h')).getByText(/Nenhuma chamada nas últimas 24 h/)).toBeInTheDocument()
    await screen.findByText('Em dia com o que está no disco')
  })

  it('com chamadas, mostra totais e chamadas por ferramenta', async () => {
    renderPage({
      project: snap({
        telemetry: {
          callsByTool: [
            { tool: 'search_hybrid', count: 3 },
            { tool: 'build_context', count: 9 },
          ],
          totalCalls: 12,
          tokensDelivered: 45678,
          lastCallAt: '2026-09-23T11:00:00Z',
        },
      }),
    })
    const u = within(section('Uso pelos agentes nas últimas 24 h'))
    expect(u.getByText('Chamadas MCP').nextSibling).toHaveTextContent('12')
    expect(u.getByText('Tokens entregues').nextSibling).toHaveTextContent('45.678')
    const bars = within(u.getByRole('list', { name: 'Chamadas por ferramenta' })).getAllByRole('listitem')
    expect(bars.map((li) => li.textContent)).toEqual(['build_context9', 'search_hybrid3'])
    await screen.findByText('Em dia com o que está no disco')
  })
})

describe('ProjectPage: economia estimada e segurança (sob demanda)', () => {
  it('desabilita as ações sob demanda e explica o motivo quando o projeto não tem path local (só federação)', () => {
    const { bridge } = renderPage({
      project: snap({
        id: 'fed',
        path: null,
        exists: false,
        counts: null,
        countsUnavailableReason: 'projeto sem caminho local (só federação)',
        git: null,
        hooksInstalled: null,
      }),
    })
    const trial = screen.getByRole('button', { name: /ver economia estimada/i })
    const scan = screen.getByRole('button', { name: /atualizar achados de segurança/i })
    expect(trial).toBeDisabled()
    expect(scan).toBeDisabled()
    expect(screen.getAllByText('Disponível apenas para projetos clonados localmente.')).toHaveLength(2)
    fireEvent.click(trial)
    fireEvent.click(scan)
    expect(bridge.runTrial).not.toHaveBeenCalled()
    expect(bridge.runSecurityScan).not.toHaveBeenCalled()
    expect(bridge.getProjectStatus).not.toHaveBeenCalled()
  })

  it('mantém as ações sob demanda habilitadas quando o projeto tem path local', async () => {
    renderPage({ project: snap({ id: 'local', path: 'C:\\a' }) })
    expect(screen.getByRole('button', { name: /ver economia estimada/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /atualizar achados de segurança/i })).toBeEnabled()
    expect(screen.queryByText('Disponível apenas para projetos clonados localmente.')).not.toBeInTheDocument()
    await screen.findByText('Em dia com o que está no disco')
  })

  it('rotula a economia como estimativa e diz quando o RAGX gasta mais tokens', async () => {
    const runTrial = vi.fn().mockResolvedValue({
      totals: { baseline_tokens: 1000, ragx_tokens: 1350, saved_ratio: -0.35, source_coverage: 0.5 },
    })
    renderPage({ project: snap({ id: 'trial-neg' }), bridge: { runTrial } })
    expect(screen.getByText('estimativa')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))

    await waitFor(() => expect(screen.getByText('mais tokens')).toBeInTheDocument())
    expect(runTrial).toHaveBeenCalledWith('trial-neg')
    expect(screen.getByText('35%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /recalcular estimativa/i })).toBeEnabled()
  })

  it('mostra a mensagem de erro real quando ragx trial falha', async () => {
    renderPage({
      project: snap({ id: 'trial-err' }),
      bridge: {
        runTrial: vi.fn().mockRejectedValue(new Error('ragx trial --json saiu com código 2: queries.yaml não encontrado')),
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))
    expect(await screen.findByText(/não foi possível calcular agora: .*queries\.yaml não encontrado/i)).toBeInTheDocument()
  })

  it('lista os arquivos bloqueados com severidade em texto e sem mostrar o trecho do segredo', async () => {
    const runSecurityScan = vi.fn().mockResolvedValue({
      root: 'C:\\a', scanned: 40, skipped: 0, policy: 'strict',
      ruleset: { version: 'builtin@1', rules: 10, disabled: [] },
      blocked: [{ path: 'config/.env', rule: 'filename-deny:env', severity: 'critical', line: 3, preview: 'AKIA-SEGREDO' }],
      redacted: [{ path: 'docs/setup.md', findings: 2 }],
    })
    renderPage({ project: snap({ id: 'scan-dirty' }), bridge: { runSecurityScan } })
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))

    await waitFor(() => expect(screen.getByText('.env')).toBeInTheDocument())
    expect(runSecurityScan).toHaveBeenCalledWith('scan-dirty')
    expect(screen.getByText('config')).toBeInTheDocument()
    expect(screen.getByText(':3')).toBeInTheDocument()
    expect(screen.getByText(/crítico/)).toBeInTheDocument()
    expect(screen.getByText('filename-deny:env')).toBeInTheDocument()
    expect(screen.queryByText(/AKIA-SEGREDO/)).not.toBeInTheDocument()
  })

  it('confirma quando o scan não encontra nada', async () => {
    renderPage({
      project: snap({ id: 'scan-clean' }),
      bridge: {
        runSecurityScan: vi.fn().mockResolvedValue({
          root: 'C:\\a', scanned: 12, skipped: 0, policy: 'strict',
          ruleset: { version: 'builtin@1', rules: 10, disabled: [] },
          blocked: [], redacted: [],
        }),
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))
    await waitFor(() => expect(screen.getByText(/nenhum segredo encontrado em 12 arquivos/i)).toBeInTheDocument())
  })

  it('mostra a mensagem de erro real quando ragx security scan falha', async () => {
    renderPage({
      project: snap({ id: 'scan-err' }),
      bridge: { runSecurityScan: vi.fn().mockRejectedValue(new Error('ragx não encontrado no PATH')) },
    })
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))
    expect(await screen.findByText(/não foi possível escanear agora: ragx não encontrado no path/i)).toBeInTheDocument()
  })

  it('mantém o último resultado ao voltar para o projeto', async () => {
    const runTrial = vi.fn().mockResolvedValue({
      totals: { baseline_tokens: 1000, ragx_tokens: 760, saved_ratio: 0.24, source_coverage: 0.63 },
    })
    const { unmount } = renderPage({ project: snap({ id: 'trial-cache' }), bridge: { runTrial } })
    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))
    await waitFor(() => expect(screen.getByText('menos tokens')).toBeInTheDocument())
    unmount()

    renderPage({ project: snap({ id: 'trial-cache' }), bridge: { runTrial } })
    expect(screen.getByText('menos tokens')).toBeInTheDocument()
    expect(screen.getByText('24%')).toBeInTheDocument()
    expect(runTrial).toHaveBeenCalledTimes(1)
  })
})

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { Onboarding } from '../Onboarding'
import { connectionChecks, installBridge } from '../../test/snap'
import type { ConnectionCheck, DiscoverResult, RagxBridge } from '../../types/ragx-bridge'

const FOLDER = { token: 'tok-root', path: 'C:/projects' }

const FOUND: DiscoverResult = {
  items: [
    { token: 'tok-a', path: 'C:/projects/juriflux', name: 'juriflux', alreadyRegistered: false },
    { token: 'tok-b', path: 'C:/projects/site', name: 'site', alreadyRegistered: false },
    { token: 'tok-c', path: 'C:/projects/ragx', name: 'ragx', alreadyRegistered: true },
  ],
  truncated: false,
}

const STEP_1 = [
  'O RAGX lê seus projetos aqui mesmo, na sua máquina, e guarda o que encontra em pedaços pequenos (chunks) com um resumo numérico de cada um (embeddings).',
  'Quando o Claude Code precisa entender o projeto, ele pergunta ao RAGX pelo MCP em vez de abrir arquivo por arquivo. Chega só o trecho que importa.',
  'Arquivos com segredos, como .env e chaves, são bloqueados antes de entrar no índice.',
  'Os hooks de git mantêm o índice na branch em que você está: ao trocar de branch, commitar ou fazer pull, o RAGX atualiza sozinho em segundo plano.',
  'Os embeddings são gerados pelo Ollama, que roda no Docker.',
]

function setup(over: Partial<RagxBridge> = {}, connections: ConnectionCheck[] | null = connectionChecks()) {
  const b = installBridge({
    pickFolder: vi.fn().mockResolvedValue(FOLDER),
    discover: vi.fn().mockResolvedValue(FOUND),
    ...over,
  })
  const onFinish = vi.fn()
  const onRefresh = vi.fn()
  render(<Onboarding connections={connections} checking={false} onRefresh={onRefresh} jobs={[]} onFinish={onFinish} />)
  return { b, onFinish, onRefresh }
}

const heading = (name: string) => screen.getByRole('heading', { level: 1, name })
const next = (name = 'Continuar') => fireEvent.click(screen.getByRole('button', { name }))

async function goToProjects() {
  next()
  next()
  expect(heading('Projetos')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
  await screen.findByRole('checkbox', { name: /juriflux/ })
  // Os dois projetos novos já vêm marcados.
  await screen.findByRole('button', { name: 'Continuar' })
}

describe('Onboarding', () => {
  it('passo 1: "Como o RAGX funciona" com o texto exato e sem "Voltar"', () => {
    setup()
    expect(heading('Como o RAGX funciona')).toBeInTheDocument()
    expect(screen.getByText('Passo 1 de 4')).toBeInTheDocument()
    for (const p of STEP_1) expect(screen.getByText(p)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Voltar' })).not.toBeInTheDocument()
    // Tela cheia: nada de barra lateral.
    expect(screen.queryByRole('navigation', { name: /principal/i })).not.toBeInTheDocument()
  })

  it('indicador de etapas marca a atual com aria-current', () => {
    setup()
    const steps = within(screen.getByRole('list', { name: 'Etapas da configuração' })).getAllByRole('listitem')
    expect(steps.map((s) => s.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('Como o RAGX funciona')]),
    )
    expect(steps).toHaveLength(4)
    expect(steps[0]).toHaveAttribute('aria-current', 'step')
    next()
    expect(steps[0]).not.toHaveAttribute('aria-current')
    expect(screen.getAllByRole('listitem').find((li) => li.getAttribute('aria-current') === 'step')).toHaveTextContent(
      'Conexões',
    )
  })

  it('passo 2: os três cards com as ações; aviso só quando algo está vermelho', () => {
    setup(undefined, connectionChecks({ ollama: { state: 'error', stateLabel: 'Não conectado' } }))
    next()
    expect(heading('Conexões')).toBeInTheDocument()
    expect(screen.getByText('Passo 2 de 4')).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Registrar para todos os projetos' })).toBeInTheDocument()
    expect(screen.getByText('Você pode continuar e resolver depois na tela Conexões.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeEnabled()
  })

  it('passo 2 sem nada vermelho não mostra o aviso', () => {
    setup()
    next()
    expect(screen.queryByText('Você pode continuar e resolver depois na tela Conexões.')).not.toBeInTheDocument()
  })

  it('passo 2: ação de conexão enfileira a tarefa', async () => {
    const { b } = setup()
    next()
    fireEvent.click(screen.getByRole('button', { name: 'Baixar nomic-embed-text' }))
    await waitFor(() => expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'ollama-pull', model: 'nomic-embed-text' }))
  })

  it('passo 3 sem projeto marcado: "Continuar sem adicionar"', () => {
    setup()
    next()
    next()
    expect(heading('Projetos')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continuar sem adicionar' })).toBeInTheDocument()
    // O fluxo embutido não tem os botões próprios do diálogo.
    expect(screen.queryByRole('button', { name: /^Adicionar \d/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar' })).not.toBeInTheDocument()
  })

  it('avança os 4 passos e "Começar" enfileira um add-project por projeto marcado', async () => {
    const { b, onFinish } = setup()
    await goToProjects()
    next('Continuar')

    expect(heading('Indexar')).toBeInTheDocument()
    expect(screen.getByText('Passo 4 de 4')).toBeInTheDocument()
    expect(
      screen.getByText('2 projeto(s) vão ser indexados. Isso roda em segundo plano; acompanhe pela fila no topo.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Instalar hooks de git/ })).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
    await waitFor(() => expect(onFinish).toHaveBeenCalledTimes(1))
    expect(b.enqueueJob).toHaveBeenCalledTimes(2)
    expect(b.enqueueJob).toHaveBeenNthCalledWith(1, { kind: 'add-project', folderToken: 'tok-a', installHooks: true })
    expect(b.enqueueJob).toHaveBeenNthCalledWith(2, { kind: 'add-project', folderToken: 'tok-b', installHooks: true })
    expect(b.setOnboardingDone).toHaveBeenCalledWith(true)
  })

  it('o checkbox de hooks vem do passo 3 e vale no "Começar"', async () => {
    const { b, onFinish } = setup()
    await goToProjects()
    fireEvent.click(screen.getByRole('checkbox', { name: /site/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Instalar hooks de git/ }))
    next()

    expect(screen.getByText(/^1 projeto\(s\) vão ser indexados/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Instalar hooks de git/ })).not.toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
    await waitFor(() => expect(onFinish).toHaveBeenCalled())
    expect(b.enqueueJob).toHaveBeenCalledTimes(1)
    expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'add-project', folderToken: 'tok-a', installHooks: false })
  })

  it('"Voltar" do passo 4 volta ao 3 com a seleção preservada', async () => {
    setup()
    await goToProjects()
    fireEvent.click(screen.getByRole('checkbox', { name: /site/ }))
    next()
    fireEvent.click(screen.getByRole('button', { name: 'Voltar' }))
    expect(heading('Projetos')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /juriflux/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /site/ })).not.toBeChecked()
  })

  it('sem projeto marcado, "Começar" só marca como feito', async () => {
    const { b, onFinish } = setup()
    next()
    next()
    next('Continuar sem adicionar')
    expect(heading('Indexar')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
    await waitFor(() => expect(onFinish).toHaveBeenCalledTimes(1))
    expect(b.enqueueJob).not.toHaveBeenCalled()
    expect(b.setOnboardingDone).toHaveBeenCalledWith(true)
  })

  it('"Pular configuração" marca como feito sem enfileirar', async () => {
    const { b, onFinish } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Pular configuração' }))
    await waitFor(() => expect(onFinish).toHaveBeenCalledTimes(1))
    expect(b.setOnboardingDone).toHaveBeenCalledWith(true)
    expect(b.enqueueJob).not.toHaveBeenCalled()
  })

  it('falha ao enfileirar fica no passo 4 com o aviso; tentar de novo só reenvia o que falhou', async () => {
    const { b, onFinish } = setup()
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(b.enqueueJob)
      .mockResolvedValueOnce({} as never)
      .mockRejectedValueOnce(new Error('recusado'))
    await goToProjects()
    next()
    fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
    expect(await screen.findByText('Não foi possível adicionar site.')).toBeInTheDocument()
    expect(onFinish).not.toHaveBeenCalled()
    expect(b.setOnboardingDone).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
    await waitFor(() => expect(onFinish).toHaveBeenCalledTimes(1))
    expect(b.enqueueJob).toHaveBeenCalledTimes(3)
    expect(b.enqueueJob).toHaveBeenLastCalledWith({ kind: 'add-project', folderToken: 'tok-b', installHooks: true })
    spy.mockRestore()
  })

  it('ao trocar de passo, o foco vai para o título do passo', () => {
    setup()
    next()
    expect(heading('Conexões')).toHaveFocus()
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import App from '../App'
import { JobButton } from '../components/project/JobButton'
import { MaintenancePanel } from '../components/project/MaintenancePanel'
import { AddProjectFlow } from '../components/project/AddProjectFlow'
import { Toaster } from '../components/ui/Toaster'
import { ConnectionsPage } from '../pages/ConnectionsPage'
import { Onboarding } from '../pages/Onboarding'
import { ProjectPage } from '../pages/ProjectPage'
import { rememberProjectTab } from '../projectTab'
import { resetToasts } from '../toast'
import { connectionChecks, installBridge, job, snap } from '../test/snap'
import type { JobView, Snapshot } from '../types/ragx-bridge'

// RAGX-0180: toda falha de ação aparece, com o motivo limpo (sem o prefixo que o Electron põe no `invoke`).
const ELECTRON_ERROR = new Error("Error invoking remote method 'ragx:enqueueJob': Error: pedido recusado: fila cheia")

beforeEach(() => {
  resetToasts()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  resetToasts()
  vi.restoreAllMocks()
})

function expectFailureToast(text: string) {
  const alert = screen.getByRole('alert')
  expect(alert).toHaveTextContent(text)
  expect(alert).not.toHaveTextContent('Error invoking remote method')
}

describe('falha de enfileirar vira aviso', () => {
  it('JobButton', async () => {
    installBridge({ enqueueJob: vi.fn().mockRejectedValue(ELECTRON_ERROR) })
    render(
      <>
        <JobButton kind="update" label="Atualizar agora" projectId="p1" jobs={[]} />
        <Toaster />
      </>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Atualizar agora' }))
    })
    expectFailureToast('Não foi possível adicionar à fila: pedido recusado: fila cheia')
  })

  it('Reindexar do zero', async () => {
    installBridge({ enqueueJob: vi.fn().mockRejectedValue(ELECTRON_ERROR) })
    render(
      <>
        <MaintenancePanel project={snap()} jobs={[]} />
        <Toaster />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Reindexar do zero' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Confirmar reindexação' }))
    })
    expectFailureToast('Não foi possível adicionar à fila: pedido recusado: fila cheia')
  })

  it('interruptor dos hooks de git', async () => {
    rememberProjectTab('manutencao')
    installBridge({
      enqueueJob: vi.fn().mockRejectedValue(ELECTRON_ERROR),
      getProjectStatus: vi.fn().mockReturnValue(new Promise(() => {})),
    })
    render(
      <>
        <ProjectPage project={snap()} jobs={[]} onBack={() => {}} />
        <Toaster />
      </>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('switch', { name: 'Hooks de git' }))
    })
    expectFailureToast('Não foi possível adicionar à fila: pedido recusado: fila cheia')
  })

  it('ação de um card de conexão', async () => {
    installBridge({ enqueueJob: vi.fn().mockRejectedValue(ELECTRON_ERROR) })
    render(
      <>
        <ConnectionsPage
          connections={connectionChecks({
            ragx: { state: 'error', stateLabel: 'Não conectado', actions: [{ kind: 'ragx-install', label: 'Instalar o RAGX' }] },
          })}
          checking={false}
          onRefresh={() => {}}
          jobs={[]}
        />
        <Toaster />
      </>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Instalar o RAGX' }))
    })
    expectFailureToast('Não foi possível adicionar à fila: pedido recusado: fila cheia')
  })
})

describe('outras falhas silenciosas', () => {
  it('copiar o texto de ajuda', async () => {
    installBridge()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('sem permissão')) },
    })
    render(
      <>
        <ConnectionsPage
          connections={connectionChecks({ ragx: { state: 'error', stateLabel: 'Não conectado', help: 'ragx --version' } })}
          checking={false}
          onRefresh={() => {}}
          jobs={[]}
        />
        <Toaster />
      </>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Copiar' }))
    })
    expectFailureToast('Não foi possível copiar: sem permissão')
  })

  it('escolher a pasta no assistente de adicionar projeto', async () => {
    installBridge({ pickFolder: vi.fn().mockRejectedValue(new Error("Error invoking remote method 'ragx:pickFolder': Error: janela fechada")) })
    render(
      <>
        <AddProjectFlow onDone={() => {}} onCancel={() => {}} />
        <Toaster />
      </>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    })
    expectFailureToast('Não foi possível abrir o seletor de pasta: janela fechada')
  })

  it('salvar o fim do assistente: avisa e segue em frente', async () => {
    installBridge({ setOnboardingDone: vi.fn().mockRejectedValue(new Error('disco cheio')) })
    const onFinish = vi.fn()
    render(
      <>
        <Onboarding connections={connectionChecks()} checking={false} onRefresh={() => {}} jobs={[]} onFinish={onFinish} />
        <Toaster />
      </>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Pular configuração' }))
    })
    expectFailureToast('Não foi possível salvar que o assistente terminou (disco cheio)')
    expect(onFinish).toHaveBeenCalled()
  })

  it('cancelar uma tarefa (o App monta o Toaster)', async () => {
    const running = job({ id: 'j9', label: 'Indexar p1', state: 'running' })
    installBridge({
      cancelJob: vi.fn().mockRejectedValue(ELECTRON_ERROR),
      listJobs: vi.fn().mockResolvedValue([running]),
      getSnapshot: vi.fn().mockResolvedValue({ projects: [snap()], generatedAt: '2026-09-23T10:00:00Z' } satisfies Snapshot),
    })
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /1 tarefa/ }))
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    })
    expectFailureToast('Não foi possível cancelar a tarefa: pedido recusado: fila cheia')
  })
})

describe('tarefa que falha em andamento', () => {
  function mountApp(initial: JobView[]) {
    let pushJobs: (j: JobView[]) => void = () => {}
    installBridge({
      listJobs: vi.fn().mockResolvedValue(initial),
      onJobs: vi.fn((cb: (j: JobView[]) => void) => {
        pushJobs = cb
        return () => {}
      }),
      getSnapshot: vi.fn().mockResolvedValue({ projects: [snap()], generatedAt: '2026-09-23T10:00:00Z' } satisfies Snapshot),
    })
    render(<App />)
    return { push: (j: JobView[]) => act(() => pushJobs(j)) }
  }

  it('running virando failed avisa com o rótulo e o erro', async () => {
    const { push } = mountApp([job({ id: 'j1', label: 'Indexar p1', state: 'running' })])
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await push([job({ id: 'j1', label: 'Indexar p1', state: 'failed', error: 'sem espaço em disco' })])
    expect(screen.getByRole('alert')).toHaveTextContent('Indexar p1: falhou. sem espaço em disco')
  })

  it('failed que já estava na primeira lista não avisa; cancelled nunca avisa', async () => {
    const { push } = mountApp([job({ id: 'old', label: 'Antiga', state: 'failed', error: 'x' })])
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await push([
      job({ id: 'old', label: 'Antiga', state: 'failed', error: 'x' }),
      job({ id: 'c1', label: 'Cancelada', state: 'cancelled' }),
    ])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('o Toaster existe no onboarding também, e a região viva está no DOM antes do primeiro aviso', async () => {
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: false }) })
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Como o RAGX funciona' })
    expect(within(document.body).getByRole('region', { name: 'Avisos' })).toHaveAttribute('aria-live', 'polite')
  })
})

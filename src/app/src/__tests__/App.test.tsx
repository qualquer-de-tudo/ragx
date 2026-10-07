import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from '../App'
import type { RagxBridge, Snapshot, UpdateState } from '../types/ragx-bridge'
import { snap } from '../test/snap'

const project = snap({ id: 'juriflux', name: 'Juriflux' })

function install(settings: { onboardingDone: boolean }, snapshot: Snapshot): RagxBridge {
  const b: RagxBridge = {
    getSnapshot: vi.fn().mockResolvedValue(snapshot),
    onSnapshot: vi.fn(() => () => {}),
    getActivity: vi.fn().mockResolvedValue([]),
    getAdoption: vi.fn().mockResolvedValue({ since: null, sessions: 0, withCalls: 0, withoutCalls: 0, unidentified: 0, callsWithoutStart: 0, byProject: [] }),
    onActivity: vi.fn(() => () => {}),
    getProjectStatus: vi.fn(),
    runTrial: vi.fn(),
    getIndexRuns: vi.fn(),
    runSecurityScan: vi.fn(),
    getConnections: vi.fn().mockResolvedValue([]),
    onConnections: vi.fn(() => () => {}),
    listJobs: vi.fn().mockResolvedValue([]),
    onJobs: vi.fn(() => () => {}),
    enqueueJob: vi.fn(),
    cancelJob: vi.fn().mockResolvedValue(true),
    pickFolder: vi.fn(),
    discover: vi.fn(),
    getSettings: vi.fn().mockResolvedValue(settings),
    setOnboardingDone: vi.fn(),
    setPricing: vi.fn(),
    setPreference: vi.fn().mockResolvedValue(undefined),
    onOpenPreferences: vi.fn(() => () => {}),
    onOpenProject: vi.fn(() => () => {}),
    setTheme: vi.fn().mockResolvedValue(undefined),
    getUpdateState: vi.fn().mockResolvedValue({ status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }),
    getAutoSetup: vi.fn().mockResolvedValue({ enabled: true, running: false, lastRunAt: null, claude: { checked: 0, installed: [], error: null }, git: { queued: [], failed: [] } }),
    runAutoSetup: vi.fn().mockResolvedValue({ enabled: true, running: false, lastRunAt: null, claude: { checked: 0, installed: [], error: null }, git: { queued: [], failed: [] } }),
    onAutoSetup: vi.fn(() => () => {}),
    checkForUpdates: vi.fn().mockResolvedValue({ status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }),
    downloadUpdate: vi.fn().mockResolvedValue({ status: 'idle', currentVersion: '1.0.0', version: null, progress: null, error: null }),
    installUpdate: vi.fn().mockResolvedValue(undefined),
    onUpdate: vi.fn(() => () => {}),
    previewContext: vi.fn(),
    runOllamaBenchmark: vi.fn(),
    getClaudeIntegration: vi.fn().mockResolvedValue({ enabled: true }),
    getMcpIntegrations: vi.fn().mockResolvedValue([]),
    setMcpIntegration: vi.fn(),
    setClaudeIntegration: vi.fn(),
    setClaudeProfile: vi.fn(),
    addClaudeProfile: vi.fn(),
    removeClaudeProfile: vi.fn(),
  }
  window.ragx = b
  return b
}

const withProject: Snapshot = { projects: [project], generatedAt: '2026-09-23T10:00:00Z', connectionsHealth: 'ok' }
const empty: Snapshot = { projects: [], generatedAt: '2026-09-23T10:00:00Z' }

describe('App', () => {
  it('abre em Projetos quando o onboarding foi feito e o hub tem projetos', async () => {
    install({ onboardingDone: true }, withProject)
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Projetos' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Projetos' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Conexões: tudo certo' })).toBeInTheDocument()
  })

  it('abre no onboarding quando ele não foi feito', async () => {
    install({ onboardingDone: false }, withProject)
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Como o RAGX funciona' })).toBeInTheDocument()
    // Tela cheia: sem barra lateral.
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('abre no onboarding quando o hub está vazio', async () => {
    install({ onboardingDone: true }, empty)
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Como o RAGX funciona' })).toBeInTheDocument()
  })

  it('"Pular configuração" leva a Projetos', async () => {
    const b = install({ onboardingDone: false }, withProject)
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Pular configuração' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Projetos' })).toBeInTheDocument()
    await waitFor(() => expect(b.setOnboardingDone).toHaveBeenCalledWith(true))
  })

  it('"Refazer configuração" em Como funciona abre o onboarding', async () => {
    install({ onboardingDone: true }, withProject)
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })
    fireEvent.click(screen.getByRole('button', { name: 'Como funciona' }))
    fireEvent.click(screen.getByRole('button', { name: 'Refazer configuração' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Como o RAGX funciona' })).toBeInTheDocument()
    expect(screen.getByText('Passo 1 de 4')).toBeInTheDocument()
  })

  it('navega pela barra lateral e pelo ponto de saúde', async () => {
    install({ onboardingDone: true }, withProject)
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })

    fireEvent.click(screen.getByRole('button', { name: 'Como funciona' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Como funciona' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Conexões: tudo certo' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Conexões' })).toBeInTheDocument()
  })

  it('versão nova: ponto em Preferências, aviso na tela uma vez por versão, e a notificação do sistema abre Preferências', async () => {
    const b = install({ onboardingDone: true }, withProject)
    let pushUpdate: (s: UpdateState) => void = () => {}
    let openPrefs: () => void = () => {}
    b.onUpdate = vi.fn((cb: (s: UpdateState) => void) => {
      pushUpdate = cb
      return () => {}
    })
    b.onOpenPreferences = vi.fn((cb: () => void) => {
      openPrefs = cb
      return () => {}
    })
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })
    expect(screen.queryByRole('img', { name: 'atualização disponível' })).not.toBeInTheDocument()

    const nova: UpdateState = { status: 'available', currentVersion: '1.0.0', version: '1.0.1', progress: null, error: null }
    act(() => pushUpdate(nova))
    expect(await screen.findByRole('img', { name: 'atualização disponível' })).toBeInTheDocument()
    expect(await screen.findByText('RAGX 1.0.1 disponível. Baixe em Preferências.')).toBeInTheDocument()

    act(() => openPrefs())
    expect(await screen.findByRole('heading', { level: 1, name: 'Preferências' })).toBeInTheDocument()
  })

  it('zera o scroll do conteúdo ao trocar de rota', async () => {
    install({ onboardingDone: true }, withProject)
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Projetos' })

    const content = document.querySelector('.content')
    expect(content).not.toBeNull()
    Object.defineProperty(content!, 'scrollTop', { value: 400, writable: true })
    expect(content!.scrollTop).toBe(400)

    fireEvent.click(screen.getByRole('button', { name: project.name }))
    await screen.findByRole('heading', { level: 1, name: project.name })

    expect(content!.scrollTop).toBe(0)
  })
})

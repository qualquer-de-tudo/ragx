import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import App from '../App'
import type { RagxBridge, Snapshot } from '../types/ragx-bridge'
import { snap } from '../test/snap'

const project = snap({ id: 'juriflux', name: 'Juriflux' })

function install(settings: { onboardingDone: boolean }, snapshot: Snapshot): RagxBridge {
  const b: RagxBridge = {
    getSnapshot: vi.fn().mockResolvedValue(snapshot),
    onSnapshot: vi.fn(() => () => {}),
    getProjectStatus: vi.fn(),
    runTrial: vi.fn(),
    runSecurityScan: vi.fn(),
    getConnections: vi.fn().mockResolvedValue([]),
    listJobs: vi.fn().mockResolvedValue([]),
    onJobs: vi.fn(() => () => {}),
    enqueueJob: vi.fn(),
    cancelJob: vi.fn().mockResolvedValue(true),
    pickFolder: vi.fn(),
    discover: vi.fn(),
    getSettings: vi.fn().mockResolvedValue(settings),
    setOnboardingDone: vi.fn(),
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
    expect(await screen.findByRole('heading', { level: 1, name: 'Configuração inicial' })).toBeInTheDocument()
    // Tela cheia: sem barra lateral.
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('abre no onboarding quando o hub está vazio', async () => {
    install({ onboardingDone: true }, empty)
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Configuração inicial' })).toBeInTheDocument()
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
})

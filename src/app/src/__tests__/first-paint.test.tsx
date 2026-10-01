import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import App from '../App'
import { writeCachedSnapshot } from '../snapshotCache'
import { installBridge, snap } from '../test/snap'
import type { ConnectionCheck, Snapshot } from '../types/ragx-bridge'

// RAGX-0182: a primeira pintura não espera o snapshot.
const live: Snapshot = {
  projects: [snap({ id: 'juriflux', name: 'Juriflux' }), snap({ id: 'ragx', name: 'ragx' })],
  generatedAt: '2026-10-01T12:00:00Z',
  connectionsHealth: 'ok',
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function delayedSnapshot() {
  let resolve: (s: Snapshot) => void = () => {}
  const getSnapshot = vi.fn(() => new Promise<Snapshot>((r) => (resolve = r)))
  return { getSnapshot, resolve: (s: Snapshot) => act(async () => resolve(s)) }
}

describe('primeira pintura', () => {
  it('sem cache: a casca e o skeleton aparecem na hora, e nunca o "Carregando…" em tela cheia', async () => {
    const d = delayedSnapshot()
    installBridge({ getSnapshot: d.getSnapshot })
    const { container } = render(<App />)
    expect(await screen.findByText('Carregando projetos')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Principal' })).toBeInTheDocument()
    expect(container.querySelector('.skeleton-card')).not.toBeNull()
    expect(screen.queryByText('Carregando…')).not.toBeInTheDocument()
    await d.resolve(live)
    expect(await screen.findByRole('heading', { level: 1, name: 'Projetos' })).toBeInTheDocument()
    expect(screen.queryByText('Carregando projetos')).not.toBeInTheDocument()
  })

  it('com cache: os cards aparecem com a faixa "atualizando…", e o vivo troca sem remontar', async () => {
    writeCachedSnapshot({ ...live, generatedAt: '2026-10-01T09:30:00Z' }, 1_000_000)
    const d = delayedSnapshot()
    installBridge({ getSnapshot: d.getSnapshot })
    render(<App />)
    const card = await screen.findByRole('article', { name: 'Juriflux' })
    expect(screen.getByText(/Dados de .*, atualizando…/)).toBeInTheDocument()
    await d.resolve(live)
    expect(screen.queryByText(/atualizando…/)).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Juriflux' })).toBe(card) // o mesmo nó: não remontou
  })

  it('o indicador de conexões diz "verificando" até a checagem real (o cache não traz connectionsHealth)', async () => {
    writeCachedSnapshot(live, 1_000_000)
    const d = delayedSnapshot()
    installBridge({ getSnapshot: d.getSnapshot, getConnections: vi.fn(() => new Promise<ConnectionCheck[]>(() => {})) })
    render(<App />)
    await screen.findByRole('article', { name: 'Juriflux' })
    expect(screen.getByRole('button', { name: 'Conexões: verificando' })).toBeInTheDocument()
  })

  it('getSnapshot rejeitando, sem cache: mostra o motivo e "Tentar de novo", que segue para Projetos', async () => {
    const getSnapshot = vi.fn().mockRejectedValueOnce(new Error('hub corrompido')).mockResolvedValueOnce(live)
    installBridge({ getSnapshot })
    render(<App />)
    expect(await screen.findByText('Não foi possível carregar os projetos')).toBeInTheDocument()
    expect(screen.getByText('hub corrompido')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Projetos' })).toBeInTheDocument()
    expect(getSnapshot).toHaveBeenCalledTimes(2)
  })

  it('destino onboarding: a casca não pisca antes dele', async () => {
    const d = delayedSnapshot()
    installBridge({ getSnapshot: d.getSnapshot, getSettings: vi.fn().mockResolvedValue({ onboardingDone: false }) })
    render(<App />)
    expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 1, name: 'Como o RAGX funciona' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument()
  })
})

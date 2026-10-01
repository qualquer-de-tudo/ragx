import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import App from '../App'
import { installBridge, snap } from '../test/snap'
import { resetToasts } from '../toast'
import type { Snapshot } from '../types/ragx-bridge'

const withProjects: Snapshot = {
  projects: [snap({ id: 'juriflux', name: 'Juriflux' }), snap({ id: 'gone', name: 'Sumido', exists: false })],
  generatedAt: '2026-10-01T12:00:00Z',
  connectionsHealth: 'ok',
}

afterEach(() => {
  cleanup()
  resetToasts()
})

async function open(over: Parameters<typeof installBridge>[0] = {}) {
  const b = installBridge({ getSnapshot: vi.fn().mockResolvedValue(withProjects), ...over })
  render(<App />)
  await screen.findByRole('heading', { level: 1, name: 'Projetos' })
  return b
}

const ctrlK = () => fireEvent.keyDown(window, { key: 'k', ctrlKey: true })

describe('atalhos no App', () => {
  it('Ctrl+K abre a paleta; "jur" + Enter abre o projeto; o foco volta ao anterior ao fechar com Esc', async () => {
    await open()
    const anterior = screen.getByRole('radio', { name: 'Grade' })
    anterior.focus()
    ctrlK()
    const input = await screen.findByRole('combobox', { name: 'Buscar comando' })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(anterior)

    ctrlK()
    const again = await screen.findByRole('combobox', { name: 'Buscar comando' })
    fireEvent.change(again, { target: { value: 'jur' } })
    fireEvent.keyDown(again, { key: 'Enter' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Juriflux' })).toBeInTheDocument()
  })

  it('Ctrl+K de novo fecha a paleta', async () => {
    await open()
    ctrlK()
    await screen.findByRole('dialog')
    ctrlK()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('"Atualizar Juriflux" chama enqueueJob com exatamente { kind, projectId }', async () => {
    const b = await open()
    ctrlK()
    const input = await screen.findByRole('combobox', { name: 'Buscar comando' })
    fireEvent.change(input, { target: { value: 'atualizar jur' } })
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' })
    })
    expect(b.enqueueJob).toHaveBeenCalledTimes(1)
    expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'update', projectId: 'juriflux' })
    expect(vi.mocked(b.enqueueJob).mock.calls[0][0]).toStrictEqual({ kind: 'update', projectId: 'juriflux' })
  })

  it('projeto sem pasta: a opção é desabilitada e nada é enfileirado', async () => {
    const b = await open()
    ctrlK()
    const input = await screen.findByRole('combobox', { name: 'Buscar comando' })
    fireEvent.change(input, { target: { value: 'atualizar sumido' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(b.enqueueJob).not.toHaveBeenCalled()
  })

  it('/ foca a busca da topbar, ? abre a ajuda, Ctrl+3 vai para Conexões', async () => {
    await open()
    fireEvent.keyDown(window, { key: '/' })
    expect(document.activeElement).toBe(screen.getByRole('searchbox', { name: 'Buscar projeto' }))
    // dentro do campo, "/" e "?" são texto
    fireEvent.keyDown(document.activeElement!, { key: '?' })
    expect(screen.queryByRole('dialog', { name: 'Atalhos de teclado' })).not.toBeInTheDocument()
    ;(document.activeElement as HTMLElement).blur()
    fireEvent.keyDown(window, { key: '?' })
    expect(screen.getByRole('dialog', { name: 'Atalhos de teclado' })).toBeInTheDocument()
    expect(document.querySelectorAll('kbd').length).toBeGreaterThan(5)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    fireEvent.keyDown(window, { key: '3', ctrlKey: true })
    expect(screen.getByRole('heading', { level: 1, name: 'Conexões' })).toBeInTheDocument()
  })

  it('a busca da topbar continua filtrando projetos, e mostra a dica Ctrl K', async () => {
    await open()
    const search = screen.getByRole('searchbox', { name: 'Buscar projeto' })
    fireEvent.change(search, { target: { value: 'jur' } })
    expect(screen.getByRole('article', { name: 'Juriflux' })).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Sumido' })).not.toBeInTheDocument()
    expect(document.querySelector('.search-kbd')).toHaveTextContent('Ctrl K')
  })

  it('no onboarding não há atalhos', async () => {
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: false }) })
    render(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Como o RAGX funciona' })
    ctrlK()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

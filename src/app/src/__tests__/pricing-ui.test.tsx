import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { TokenSavings } from '../components/project/TokenSavings'
import { ProjectsPage } from '../pages/ProjectsPage'
import { ActivityPage } from '../pages/ActivityPage'
import { Toaster } from '../components/ui/Toaster'
import { installBridge, snap } from '../test/snap'
import { resetToasts } from '../toast'
import type { SavingsSeries } from '../../electron/data/types'
import type { ActivityEvent } from '../types/ragx-bridge'

// RAGX-0186: o preço é da pessoa; sem ele nenhuma tela mostra dinheiro.
const savings: SavingsSeries = {
  days: [{ date: '2026-09-30', baseline: 5_000_000, delivered: 1_000_000, calls: 4 }],
  baseline: 5_000_000, delivered: 1_000_000, calls: 4,
}
const pricing = { currency: 'BRL' as const, perMTokInput: 3 } // 4 mi economizados x 3 = R$ 12,00
const norm = (s: string | null) => (s ?? '').replace(/\s/g, ' ')

afterEach(() => {
  cleanup()
  resetToasts()
  vi.restoreAllMocks()
})

describe('TokenSavings com e sem preço', () => {
  it('sem preço: só o convite, nunca "R$ 0,00"', async () => {
    installBridge()
    render(<TokenSavings projectId="p" projectPath="C:/p" savings={savings} />)
    expect(screen.getByText(/Informe quanto você paga por milhão de tokens de entrada/)).toBeInTheDocument()
    expect(screen.queryByText(/R\$/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Configurar preço' })).toBeInTheDocument()
  })

  it('com preço: valor, selo "estimativa" e a legenda do que o valor é', async () => {
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, pricing }) })
    render(<TokenSavings projectId="p" projectPath="C:/p" savings={savings} />)
    await waitFor(() => expect(norm(document.body.textContent)).toContain('R$ 12,00'))
    expect(document.querySelector('.savings-money .badge')).toHaveTextContent('estimativa')
    expect(screen.getByText(/não considera a leitura de cache de prompt/)).toBeInTheDocument()
  })

  it('configurar: valida, grava pela ponte e passa a mostrar o valor', async () => {
    const b = installBridge()
    render(<TokenSavings projectId="p" projectPath="C:/p" savings={savings} />)
    fireEvent.click(screen.getByRole('button', { name: 'Configurar preço' }))
    const input = screen.getByRole('textbox', { name: /Preço por 1 milhão/ })
    fireEvent.change(input, { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar' }))
    expect(screen.getByRole('alert')).toHaveTextContent('maior que 0')
    expect(b.setPricing).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: '3,5' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Salvar' }))
    })
    expect(b.setPricing).toHaveBeenCalledWith({ currency: 'BRL', perMTokInput: 3.5 })
    await waitFor(() => expect(norm(document.body.textContent)).toContain('R$ 14,00'))
  })

  it('falha ao gravar aparece num aviso e o diálogo continua aberto', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    installBridge({ setPricing: vi.fn().mockRejectedValue(new Error('disco cheio')) })
    render(
      <>
        <TokenSavings projectId="p" projectPath="C:/p" savings={savings} />
        <Toaster />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Configurar preço' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Preço por 1 milhão/ }), { target: { value: '3' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Salvar' }))
    })
    expect(screen.getByText(/Não foi possível salvar o preço: disco cheio/)).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Configurar preço' })).toBeInTheDocument()
  })
})

describe('resumo de Projetos e Atividade', () => {
  const project = snap({
    id: 'a', name: 'A',
    telemetry: { callsByTool: [], totalCalls: 4, tokensDelivered: 0, lastCallAt: null, savings },
  })

  it('Projetos: nota com valor e "(estimativa)" só com preço', async () => {
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, pricing }) })
    render(<ProjectsPage projects={[project]} jobs={[]} query="" onOpen={vi.fn()} />)
    await waitFor(() => expect(norm(document.body.textContent)).toContain('R$ 12,00 (estimativa)'))
  })

  it('Projetos sem preço: nenhuma moeda', async () => {
    installBridge()
    render(<ProjectsPage projects={[project]} jobs={[]} query="" onOpen={vi.fn()} />)
    await act(async () => {})
    expect(document.body.textContent).not.toMatch(/R\$|estimativa/)
  })

  it('Atividade: valor do dia só com preço e com medição', async () => {
    const ev = {
      id: 'e1', ts: new Date().toISOString(), projectId: 'a', projectName: 'A', kind: 'mcp', name: 'build_context',
      ms: 1, ok: true, tokensDelivered: 1_000_000, baselineTokens: 5_000_000, errCode: null, respChars: 1, respTokens: 1,
      client: 'claude-code', profile: null, session: null,
    } as ActivityEvent
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, pricing }) })
    render(<ActivityPage events={[ev]} projects={[project]} jobs={[]} now={Date.now()} onOpen={vi.fn()} />)
    await waitFor(() => expect(norm(document.body.textContent)).toContain('R$ 12,00 (estimativa)'))
  })
})

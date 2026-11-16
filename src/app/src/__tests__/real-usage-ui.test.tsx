import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActivityPage } from '../pages/ActivityPage'
import { ProjectPage } from '../pages/ProjectPage'
import { installBridge, snap, usageBlock, usageMetrics, usageReport } from '../test/snap'
import { rememberProjectTab } from '../projectTab'
import { forgetUsage } from '../hooks/useUsage'
import type { AdoptionSummary, UsageBlock } from '../types/ragx-bridge'

afterEach(() => {
  cleanup()
  forgetUsage()
  rememberProjectTab('geral')
})

const juriflux: UsageBlock = usageBlock({
  sessions: 64,
  all: { sessions: 64, median: usageMetrics({ turns: 6, totalTokens: 200_000, cacheReadTokens: 150_000, searchCalls: 2, readCalls: 3 }), total: usageMetrics() },
  withRagx: {
    sessions: 4,
    median: usageMetrics({ turns: 822, totalTokens: 216_000_000, ragxCalls: 1, searchCalls: 505, searchResultChars: 1_133_196 }),
    total: usageMetrics(),
  },
  withoutRagx: {
    sessions: 60,
    median: usageMetrics({ turns: 4, totalTokens: 199_782, searchCalls: 2, searchResultChars: 9_340 }),
    total: usageMetrics(),
  },
  adoption: { sessions: 64, withRagx: 4, hinted: 25, reminded: 20, ragxAfterReminder: 3 },
})

const report = usageReport({
  sessionsScanned: 70,
  overall: juriflux,
  projects: [
    { id: 'p1', name: 'Juriflux', ...juriflux },
    { id: 'p2', name: 'ragx', ...usageBlock({ sessions: 1, adoption: { sessions: 1, withRagx: 1, hinted: 1, reminded: 0, ragxAfterReminder: 0 } }) },
  ],
})

const adoption: AdoptionSummary = {
  since: null, sessions: 38, withCalls: 3, withoutCalls: 35, unidentified: 0, callsWithoutStart: 0, byProject: [],
}

function region(name: string) {
  return within(screen.getByRole('region', { name }))
}

describe('Atividade: consumo real lido das sessões', () => {
  it('mostra o consumo real como observação, com a adoção e a conversão do lembrete; a adoção do log sai', async () => {
    installBridge({ getUsage: vi.fn().mockResolvedValue(report), getAdoption: vi.fn().mockResolvedValue(adoption) })
    render(<ActivityPage events={[]} projects={[snap({ id: 'p1', name: 'Juriflux' })]} jobs={[]} now={Date.now()} onOpen={vi.fn()} />)
    const s = within(await screen.findByRole('region', { name: 'Consumo real nas sessões do Claude Code' }))
    expect(s.getByText('observação')).toBeInTheDocument()
    expect(s.getByText(/4 de 64 sessões chamaram o RAGX \(6%\)\. O lembrete apareceu em 20; 3 chamaram o RAGX depois dele\./)).toBeInTheDocument()
    expect(s.getByText(/Observação, não experimento/)).toBeInTheDocument()
    expect(s.getByText('Juriflux: 4 de 64 · depois do lembrete: 3 de 20')).toBeInTheDocument()
    expect(s.getByText('ragx: 1 de 1')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Adoção pelos agentes')).not.toBeInTheDocument())
    // o número antigo fica, rotulado como estimativa
    expect(screen.getByText('Economia estimada')).toBeInTheDocument()
  })

  it('sem sessões lidas (ou CLI antiga), a adoção continua vindo do log do servidor', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    installBridge({ getUsage: vi.fn().mockRejectedValue(new Error("No such command 'usage'")), getAdoption: vi.fn().mockResolvedValue(adoption) })
    render(<ActivityPage events={[]} projects={[]} jobs={[]} now={Date.now()} onOpen={vi.fn()} />)
    expect(await screen.findByText(/3 de 38 sessões chamaram o RAGX/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Consumo real nas sessões do Claude Code' })).not.toBeInTheDocument()
  })
})

describe('Detalhe do projeto: consumo real e economia estimada', () => {
  function abrir(getUsage = vi.fn().mockResolvedValue(report)) {
    rememberProjectTab('economia')
    installBridge({ getUsage })
    render(<ProjectPage project={snap({ id: 'p1', name: 'Juriflux' })} jobs={[]} onBack={vi.fn()} />)
    return getUsage
  }

  it('a aba "Consumo de tokens" abre com o consumo real, com e sem RAGX lado a lado', async () => {
    abrir()
    await screen.findByText(/4 de 64 sessões chamaram o RAGX/)
    const s = region('Consumo real')
    expect(s.getByText('observação')).toBeInTheDocument()
    const linha = (rotulo: string) => s.getByRole('rowheader', { name: rotulo }).closest('tr') as HTMLElement
    expect(within(linha('Turnos (respostas do modelo)')).getAllByRole('cell').map((c) => c.textContent)).toEqual(['822', '4'])
    expect(within(linha('Buscas')).getAllByRole('cell').map((c) => c.textContent)).toEqual(['505', '2'])
    // 1.133.196 caracteres / 4 = 283.299 tokens (compacto: 283,3 mil)
    expect(within(linha('Resultado de busca (≈ tokens)')).getAllByRole('cell')[0]).toHaveTextContent('283,3 mil')
    expect(s.getByRole('columnheader', { name: 'Com RAGX (4)' })).toBeInTheDocument()
    expect(s.getByRole('columnheader', { name: 'Sem RAGX (60)' })).toBeInTheDocument()
    // a economia antiga continua, como estimativa contra arquivos inteiros
    expect(screen.getByRole('region', { name: 'Economia estimada (contra arquivos inteiros)' })).toBeInTheDocument()
  })

  it('projeto sem sessões: explica, sem tabela', async () => {
    abrir(vi.fn().mockResolvedValue(usageReport()))
    const s = within(await screen.findByRole('region', { name: 'Consumo real' }))
    expect(await s.findByText(/Nenhuma sessão do Claude Code neste projeto nos últimos 14 dias/)).toBeInTheDocument()
    expect(s.queryByRole('table')).not.toBeInTheDocument()
  })

  it('falha na leitura: diz o motivo, e a economia estimada segue na tela', async () => {
    abrir(vi.fn().mockRejectedValue(new Error("Error invoking remote method 'ragx:getUsage': Error: saiu com código 2")))
    const s = within(await screen.findByRole('region', { name: 'Consumo real' }))
    expect(await s.findByText('Não foi possível ler as sessões do Claude Code: saiu com código 2')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Economia estimada (contra arquivos inteiros)' })).toBeInTheDocument()
  })

  it('"Atualizar" pede uma leitura nova (force)', async () => {
    const getUsage = abrir()
    await screen.findByText(/4 de 64 sessões chamaram o RAGX/)
    fireEvent.click(region('Consumo real').getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(getUsage).toHaveBeenLastCalledWith(true))
    expect(getUsage).toHaveBeenNthCalledWith(1, false)
  })

  it('na visão geral, a adoção do projeto vem das sessões', async () => {
    rememberProjectTab('geral')
    installBridge({ getUsage: vi.fn().mockResolvedValue(report) })
    render(<ProjectPage project={snap({ id: 'p1', name: 'Juriflux' })} jobs={[]} onBack={vi.fn()} />)
    expect(await screen.findByText('Sessões que chamaram o RAGX nos últimos 14 dias: 4 de 64')).toBeInTheDocument()
  })
})

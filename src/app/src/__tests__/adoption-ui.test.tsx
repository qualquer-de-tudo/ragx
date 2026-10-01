import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { ActivityPage } from '../pages/ActivityPage'
import { ProjectPage } from '../pages/ProjectPage'
import { installBridge, snap } from '../test/snap'
import { rememberProjectTab } from '../projectTab'
import type { AdoptionSummary } from '../types/ragx-bridge'

afterEach(() => {
  cleanup()
  rememberProjectTab('geral')
})

const adoption: AdoptionSummary = {
  since: '2026-09-18T10:00:00',
  sessions: 38,
  withCalls: 3,
  withoutCalls: 35,
  unidentified: 4,
  callsWithoutStart: 1,
  byProject: [
    { projectId: 'p1', projectName: 'Juriflux', sessions: 30, withCalls: 2 },
    { projectId: 'p2', projectName: 'Outro', sessions: 8, withCalls: 1 },
  ],
}

function activity() {
  return render(<ActivityPage events={[]} projects={[snap({ id: 'p1', name: 'Juriflux' })]} jobs={[]} now={Date.now()} onOpen={vi.fn()} />)
}

describe('Atividade: adoção pelos agentes', () => {
  it('mostra "3 de 38 sessões chamaram o RAGX (8%)", o período real e a lista por projeto', async () => {
    installBridge({ getAdoption: vi.fn().mockResolvedValue(adoption) })
    activity()
    expect(await screen.findByText(/3 de 38 sessões chamaram o RAGX \(8%\) · desde 18\/09/)).toBeInTheDocument()
    expect(screen.getByText('Juriflux: 2 de 30')).toBeInTheDocument()
    expect(screen.getByText('Outro: 1 de 8')).toBeInTheDocument()
    expect(screen.getByText(/4 evento\(s\) sem identificação de sessão; 1 sessão\(ões\) com chamadas e sem início registrado/)).toBeInTheDocument()
  })

  it('zero sessões: "Nenhuma sessão registrada ainda", nunca "0%"', async () => {
    installBridge({ getAdoption: vi.fn().mockResolvedValue({ ...adoption, sessions: 0, withCalls: 0, withoutCalls: 0, unidentified: 0, callsWithoutStart: 0, byProject: [], since: null }) })
    activity()
    expect(await screen.findByText('Nenhuma sessão registrada ainda.')).toBeInTheDocument()
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument()
  })

  it('falha na leitura: a seção some e a tela segue', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    installBridge({ getAdoption: vi.fn().mockRejectedValue(new Error('x')) })
    activity()
    await waitFor(() => expect(console.error).toHaveBeenCalled())
    expect(screen.queryByText('Adoção pelos agentes')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Atividade' })).toBeInTheDocument()
  })
})

describe('Detalhe do projeto: sessões que chamaram o RAGX', () => {
  const comUso = snap({
    id: 'p1', name: 'Juriflux',
    telemetry: { callsByTool: [{ tool: 'build_context', count: 3 }], totalCalls: 3, tokensDelivered: 10, lastCallAt: null },
  })

  it('mostra "x de y" do projeto quando há sessão', async () => {
    installBridge({ getAdoption: vi.fn().mockResolvedValue(adoption), getProjectStatus: vi.fn(() => new Promise(() => {})) })
    render(<ProjectPage project={comUso} jobs={[]} onBack={vi.fn()} />)
    expect(await screen.findByText('Sessões que chamaram o RAGX: 2 de 30')).toBeInTheDocument()
  })

  it('sem sessão do projeto, a linha não aparece', async () => {
    installBridge({ getAdoption: vi.fn().mockResolvedValue({ ...adoption, byProject: [] }), getProjectStatus: vi.fn(() => new Promise(() => {})) })
    render(<ProjectPage project={comUso} jobs={[]} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Chamadas MCP')).toBeInTheDocument())
    expect(screen.queryByText(/Sessões que chamaram o RAGX/)).not.toBeInTheDocument()
  })
})

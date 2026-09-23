import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ProjectDetail } from '../ProjectDetail'
import type { ProjectSnapshot } from '../../types/ragx-bridge'

function makeProject(path: string | null): ProjectSnapshot {
  return {
    id: '1',
    name: 'projeto-a',
    path,
    cloned: path !== null,
    embeddingModel: 'x',
    visibility: 'workspace',
    status: 'ok',
    chunks: 10,
    lastSync: null,
    stats: { documents: 5, chunks: 10, embeddings: 10 },
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
  }
}

describe('ProjectDetail', () => {
  it('desabilita as acoes sob demanda e explica o motivo quando o projeto nao tem path local (só federação)', () => {
    render(<ProjectDetail project={makeProject(null)} />)

    expect(screen.getByRole('button', { name: /ver economia estimada/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /atualizar achados de segurança/i })).toBeDisabled()
    expect(
      screen.getAllByText(/disponível apenas para projetos clonados localmente/i),
    ).toHaveLength(2)
  })

  it('mantem as acoes sob demanda habilitadas quando o projeto tem path local', () => {
    render(<ProjectDetail project={makeProject('C:\\a')} />)

    expect(screen.getByRole('button', { name: /ver economia estimada/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /atualizar achados de segurança/i })).toBeEnabled()
    expect(
      screen.queryByText(/disponível apenas para projetos clonados localmente/i),
    ).not.toBeInTheDocument()
  })

  it('mostra a mensagem de erro real quando ragx trial falha (ex.: arquivo de queries ausente)', async () => {
    window.ragx = {
      getSnapshot: vi.fn(),
      onSnapshot: vi.fn(() => () => {}),
      runTrial: vi.fn().mockRejectedValue(new Error('ragx trial --json saiu com código 2: UsageError: queries.yaml não encontrado')),
      runSecurityScan: vi.fn(),
    }

    render(<ProjectDetail project={makeProject('C:\\a')} />)
    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))

    await waitFor(() =>
      expect(screen.getByText(/não foi possível calcular agora: .*queries\.yaml não encontrado/i)).toBeInTheDocument(),
    )
  })

  it('mostra a mensagem de erro real quando ragx security scan falha', async () => {
    window.ragx = {
      getSnapshot: vi.fn(),
      onSnapshot: vi.fn(() => () => {}),
      runTrial: vi.fn(),
      runSecurityScan: vi.fn().mockRejectedValue(new Error('ragx não encontrado no PATH')),
    }

    render(<ProjectDetail project={makeProject('C:\\a')} />)
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))

    await waitFor(() =>
      expect(screen.getByText(/não foi possível escanear agora: ragx não encontrado no path/i)).toBeInTheDocument(),
    )
  })
})

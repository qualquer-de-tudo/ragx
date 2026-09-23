import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
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
})

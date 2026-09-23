import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProjectList } from '../ProjectList'
import type { ProjectSnapshot } from '../../types/ragx-bridge'

const projects: ProjectSnapshot[] = [
  {
    id: '1', name: 'projeto-a', path: 'C:\\a', cloned: true, embeddingModel: 'x',
    visibility: 'workspace', status: 'ok', chunks: 10, lastSync: null,
    stats: { documents: 5, chunks: 10, embeddings: 10 },
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
  },
  {
    id: '2', name: 'projeto-b', path: 'C:\\b', cloned: true, embeddingModel: 'x',
    visibility: 'workspace', status: 'degraded', chunks: 3, lastSync: null,
    stats: { unavailable: true, reason: 'pasta não existe' },
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
  },
]

describe('ProjectList', () => {
  it('lista os nomes dos projetos e o status de cada um', () => {
    render(<ProjectList projects={projects} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText('projeto-a')).toBeInTheDocument()
    expect(screen.getByText('projeto-b')).toBeInTheDocument()
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('chama onSelect com o id do projeto clicado', () => {
    const onSelect = vi.fn()
    render(<ProjectList projects={projects} selectedId={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('projeto-b'))
    expect(onSelect).toHaveBeenCalledWith('2')
  })

  it('mostra mensagem quando a lista esta vazia', () => {
    render(<ProjectList projects={[]} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText(/nenhum projeto/i)).toBeInTheDocument()
  })
})

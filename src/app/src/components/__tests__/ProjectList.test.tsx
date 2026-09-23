import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProjectList } from '../ProjectList'
import type { ProjectSnapshot } from '../../types/ragx-bridge'

function project(id: string, name: string, extra: Partial<ProjectSnapshot> = {}): ProjectSnapshot {
  return {
    id, name, path: `C:\\projects\\grupo\\${name}`, cloned: true, embeddingModel: 'x',
    visibility: 'workspace', status: 'ok', chunks: 0, lastSync: null,
    stats: { documents: 5, chunks: 10, embeddings: 10 },
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0 },
    ...extra,
  }
}

const projects: ProjectSnapshot[] = [
  project('1', 'projeto-a'),
  project('2', 'projeto-b', { status: 'degraded', stats: { unavailable: true, reason: 'pasta não existe' } }),
]

describe('ProjectList', () => {
  it('lista os nomes e só destaca o status quando ele não é ok', () => {
    render(<ProjectList projects={projects} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText('projeto-a')).toBeInTheDocument()
    expect(screen.getByText('projeto-b')).toBeInTheDocument()
    expect(screen.getByText('degradado')).toBeInTheDocument()
    expect(screen.queryByText('ok')).not.toBeInTheDocument()
  })

  it('mostra a pasta de origem, relativa à pasta comum, para distinguir projetos com o mesmo nome', () => {
    const sameName = [
      project('1', 'src', { path: 'C:\\projects\\socix\\hns\\backend\\src' }),
      project('2', 'src', { path: 'C:\\projects\\gsisten\\src' }),
    ]
    render(<ProjectList projects={sameName} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText('socix/hns/backend')).toBeInTheDocument()
    expect(screen.getByText('gsisten')).toBeInTheDocument()
  })

  it('chama onSelect com o id do projeto clicado', () => {
    const onSelect = vi.fn()
    render(<ProjectList projects={projects} selectedId={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('projeto-b'))
    expect(onSelect).toHaveBeenCalledWith('2')
  })

  it('mostra mensagem quando a lista esta vazia', () => {
    render(<ProjectList projects={[]} selectedId={null} onSelect={vi.fn()} />)
    expect(screen.getByText(/nenhum projeto no hub/i)).toBeInTheDocument()
  })

  it('não diz que o hub está vazio enquanto ainda carrega', () => {
    render(<ProjectList projects={[]} selectedId={null} onSelect={vi.fn()} loading />)
    expect(screen.getByText(/lendo o hub/i)).toBeInTheDocument()
    expect(screen.queryByText(/nenhum projeto no hub/i)).not.toBeInTheDocument()
  })

  it('filtra por nome quando há muitos projetos', () => {
    const many = ['alfa', 'beta', 'gama', 'delta', 'epsilon', 'zeta', 'eta'].map((n, i) => project(String(i), n))
    render(<ProjectList projects={many} selectedId={null} onSelect={vi.fn()} />)
    fireEvent.change(screen.getByRole('searchbox', { name: /filtrar projetos/i }), { target: { value: 'et' } })
    expect(screen.getByText('beta')).toBeInTheDocument()
    expect(screen.getByText('zeta')).toBeInTheDocument()
    expect(screen.queryByText('alfa')).not.toBeInTheDocument()
  })
})

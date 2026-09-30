import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ClaudeProfiles } from '../ClaudeProfiles'
import type { ClaudeToggle } from '../../../hooks/useClaudeIntegration'

function claude(over: Partial<ClaudeToggle> = {}): ClaudeToggle {
  return {
    enabled: true,
    busy: false,
    error: null,
    changed: false,
    toggle: vi.fn(),
    profiles: [
      { id: 'claude-code', name: 'padrão', label: 'Claude Code', dir: 'C:/u/.claude', enabled: true, hint: true, added: false },
      { id: 'claude-code:empresa', name: 'empresa', label: 'Claude Code (empresa)', dir: 'C:/u/.claude-empresa', enabled: false, hint: false, added: false },
      { id: 'claude-code:cliente', name: 'cliente', label: 'Claude Code (cliente)', dir: 'D:/contas/cliente', enabled: true, hint: false, added: true },
    ],
    setProfile: vi.fn(),
    addProfile: vi.fn(),
    removeProfile: vi.fn(),
    ...over,
  }
}

const item = (nome: string) => screen.getByText(nome, { selector: '.profile-name' }).closest('li') as HTMLElement

describe('ClaudeProfiles', () => {
  it('um item por perfil, com a pasta, a origem e o interruptor de cada um', () => {
    render(<ClaudeProfiles claude={claude()} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(within(item('empresa')).getByText('C:/u/.claude-empresa')).toBeInTheDocument()
    expect(within(item('empresa')).getByText('detectado')).toBeInTheDocument()
    expect(within(item('cliente')).getByText('adicionado')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'RAGX no perfil empresa' })).toHaveAttribute('aria-checked', 'false')
    expect(within(item('cliente')).getByText('sem a dica de início de sessão')).toBeInTheDocument()
    expect(screen.getByText(/RAGX ligado em 2 de 3/)).toBeInTheDocument()
  })

  it('o interruptor liga e desliga só aquele perfil', () => {
    const c = claude()
    render(<ClaudeProfiles claude={c} />)
    fireEvent.click(screen.getByRole('switch', { name: 'RAGX no perfil empresa' }))
    expect(c.setProfile).toHaveBeenCalledWith('claude-code:empresa', true)
    fireEvent.click(screen.getByRole('switch', { name: 'RAGX no perfil padrão' }))
    expect(c.setProfile).toHaveBeenCalledWith('claude-code', false)
  })

  it('só o perfil adicionado tem "Remover", que pede o segundo clique', () => {
    const c = claude()
    render(<ClaudeProfiles claude={c} />)
    expect(within(item('empresa')).queryByRole('button', { name: 'Remover' })).not.toBeInTheDocument()
    fireEvent.click(within(item('cliente')).getByRole('button', { name: 'Remover' }))
    expect(c.removeProfile).not.toHaveBeenCalled()
    fireEvent.click(within(item('cliente')).getByRole('button', { name: 'Tirar o RAGX e remover' }))
    expect(c.removeProfile).toHaveBeenCalledWith('claude-code:cliente')
  })

  it('"Adicionar perfil" pede a pasta; enquanto altera, tudo espera; erro aparece', () => {
    const c = claude()
    const { rerender } = render(<ClaudeProfiles claude={c} />)
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar perfil' }))
    expect(c.addProfile).toHaveBeenCalled()

    rerender(<ClaudeProfiles claude={claude({ busy: true })} />)
    expect(screen.getByRole('button', { name: 'Adicionar perfil' })).toBeDisabled()
    expect(screen.getAllByRole('switch').every((s) => (s as HTMLButtonElement).disabled)).toBe(true)

    rerender(<ClaudeProfiles claude={claude({ error: 'Não consegui alterar o Claude Code: perfil sumiu' })} />)
    expect(screen.getByText(/perfil sumiu/)).toHaveClass('is-critical')
  })
})

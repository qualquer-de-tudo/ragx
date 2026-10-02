import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AutoSetupCard } from '../AutoSetupCard'
import { claudeHooksRow, gitHooksRow, lastRunSummary } from '../../../hookRows'
import { snap } from '../../../test/snap'
import type { AutoSetupView } from '../../../hooks/useAutoSetup'
import type { AutoSetupState, ClaudeProfile } from '../../../types/ragx-bridge'

function profile(over: Partial<ClaudeProfile> = {}): ClaudeProfile {
  return {
    id: 'claude-code', name: 'padrão', label: 'Claude Code', dir: 'C:/u/.claude',
    enabled: true, hint: true, touch: true, nudge: true, added: false, ...over,
  }
}

function state(over: Partial<AutoSetupState> = {}): AutoSetupState {
  return {
    enabled: true, running: false, lastRunAt: '2026-10-02T12:00:00Z',
    claude: { checked: 1, installed: [], error: null }, git: { queued: [], failed: [] }, ...over,
  }
}

describe('linhas de hooks', () => {
  it('Claude: sem perfil, perfil desligado, em dia e faltando', () => {
    expect(claudeHooksRow([]).tone).toBe('idle')
    const desligado = claudeHooksRow([profile({ enabled: false, touch: false })])
    expect(desligado.tone).toBe('idle')
    expect(desligado.text).toMatch(/desligado em todos os perfis/)
    const emDia = claudeHooksRow([profile(), profile({ id: 'claude-code:empresa', name: 'empresa' })])
    expect(emDia.tone).toBe('ok')
    expect(emDia.text).toMatch(/Em dia em 2 perfis/)
    const falta = claudeHooksRow([profile(), profile({ id: 'claude-code:empresa', name: 'empresa', touch: false })])
    expect(falta.tone).toBe('warn')
    expect(falta.text).toMatch(/Faltam hooks em empresa/)
  })

  it('Claude: perfil desligado nunca conta como "faltando"', () => {
    const row = claudeHooksRow([profile(), profile({ id: 'x', name: 'vitor', enabled: false, touch: false, nudge: false })])
    expect(row.tone).toBe('ok')
  })

  it('Git: só conta projeto local com status conhecido', () => {
    expect(gitHooksRow([]).tone).toBe('idle')
    expect(gitHooksRow([snap({ hooksInstalled: null }), snap({ id: 'p2', path: null })]).tone).toBe('idle')
    expect(gitHooksRow([snap({ hooksInstalled: true }), snap({ id: 'p2', hooksInstalled: true })]).text).toMatch(/Em dia em 2 projetos/)
    const falta = gitHooksRow([snap({ name: 'alfa', hooksInstalled: false }), snap({ id: 'p2', hooksInstalled: true })])
    expect(falta.tone).toBe('warn')
    expect(falta.text).toBe('1 de 2 sem hooks: alfa. O ajuste instala sozinho.')
  })

  it('lista muitos nomes com "e mais N"', () => {
    const muitos = Array.from({ length: 6 }, (_, i) => snap({ id: `p${i}`, name: `proj${i}`, hooksInstalled: false }))
    expect(gitHooksRow(muitos).text).toContain('proj0, proj1, proj2 e mais 3')
  })

  it('resumo da última rodada', () => {
    expect(lastRunSummary(state())).toBe('Nada a instalar.')
    expect(
      lastRunSummary(state({ claude: { checked: 1, installed: ['empresa: aviso de edição'], error: null }, git: { queued: ['alfa'], failed: [] } })),
    ).toBe('Instalou: Claude Code, empresa: aviso de edição. Git, hooks em alfa.')
  })
})

describe('AutoSetupCard', () => {
  const view = (over: Partial<AutoSetupView> = {}): AutoSetupView => ({ state: state(), run: vi.fn(), setEnabled: vi.fn(), ...over })

  it('mostra as duas linhas, a última verificação e "Ajustar agora" roda o ajuste', () => {
    const auto = view()
    render(<AutoSetupCard auto={auto} profiles={[profile()]} projects={[snap({ hooksInstalled: true })]} />)
    expect(screen.getByRole('heading', { name: 'Ajuste automático' })).toBeInTheDocument()
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('Git')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ajustar agora' }))
    expect(auto.run).toHaveBeenCalledTimes(1)
  })

  it('o interruptor liga e desliga a preferência', () => {
    const auto = view()
    render(<AutoSetupCard auto={auto} profiles={[]} projects={[]} />)
    fireEvent.click(screen.getByRole('switch', { name: 'Ajuste automático dos hooks' }))
    expect(auto.setEnabled).toHaveBeenCalledWith(false)
  })

  it('desligado: explica que nada é instalado e bloqueia "Ajustar agora"', () => {
    render(<AutoSetupCard auto={view({ state: state({ enabled: false }) })} profiles={[]} projects={[]} />)
    expect(screen.getByText(/nada é instalado sem você pedir/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ajustar agora' })).toBeDisabled()
  })

  it('rodando: mostra "Ajustando…" e bloqueia o botão; antes do primeiro estado, o interruptor fica travado', () => {
    const { rerender } = render(<AutoSetupCard auto={view({ state: state({ running: true }) })} profiles={[]} projects={[]} />)
    expect(screen.getByText('Ajustando…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ajustar agora' })).toBeDisabled()
    rerender(<AutoSetupCard auto={view({ state: null })} profiles={[]} projects={[]} />)
    expect(screen.getByRole('switch', { name: 'Ajuste automático dos hooks' })).toBeDisabled()
  })

  it('erro do heal e projeto recusado pela fila aparecem como alerta', () => {
    const { rerender } = render(
      <AutoSetupCard auto={view({ state: state({ claude: { checked: 0, installed: [], error: 'Comando não encontrado: ragx' } }) })} profiles={[]} projects={[]} />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Comando não encontrado: ragx')
    rerender(<AutoSetupCard auto={view({ state: state({ git: { queued: [], failed: ['alfa'] } }) })} profiles={[]} projects={[]} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Não consegui enfileirar: alfa.')
  })
})

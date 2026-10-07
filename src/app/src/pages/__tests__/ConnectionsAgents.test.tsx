import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConnectionsPage } from '../ConnectionsPage'
import { Onboarding } from '../Onboarding'
import { connectionChecks, installBridge } from '../../test/snap'
import type { McpIntegration } from '../../types/ragx-bridge'

function page() {
  return render(<ConnectionsPage connections={connectionChecks()} checking={false} onRefresh={vi.fn()} jobs={[]} />)
}

describe('conexões por agente', () => {
  it('abas navegam por teclado e ambiente não exige Claude', () => {
    installBridge()
    page()
    const environment = screen.getByRole('tab', { name: 'Ambiente' })
    expect(environment).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('article', { name: 'Claude Code' })).not.toBeInTheDocument()
    expect(screen.getByText('1 de 2 pede atenção')).toBeInTheDocument()
    fireEvent.keyDown(environment, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Claude Code' })).toHaveFocus()
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Claude Code' }), { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Outros agentes' })).toHaveFocus()
  })

  it('conecta Codex após confirmação e permite desligar', async () => {
    const bridge = installBridge()
    const clients = await bridge.getMcpIntegrations()
    let confirm: (clients: McpIntegration[]) => void = () => {}
    bridge.setMcpIntegration = vi.fn().mockImplementationOnce(() => new Promise<McpIntegration[]>((resolve) => { confirm = resolve }))
      .mockResolvedValueOnce(clients)
    page()
    fireEvent.click(screen.getByRole('tab', { name: 'Codex' }))
    const toggle = await screen.findByRole('switch', { name: 'RAGX no Codex' })
    await waitFor(() => expect(toggle).toBeEnabled())
    fireEvent.click(toggle)
    expect(bridge.setMcpIntegration).toHaveBeenCalledWith('codex', true)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(toggle).toBeDisabled()
    confirm(clients.map((c) => c.id === 'codex' ? { ...c, enabled: true } : c))
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'))
    expect(screen.getByText('Reabra o Codex para carregar a configuração nova.')).toBeInTheDocument()
    fireEvent.click(toggle)
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'))
    expect(bridge.setMcpIntegration).toHaveBeenLastCalledWith('codex', false)
  })

  it('mantém desligado e informa falha, sem sucesso otimista', async () => {
    const bridge = installBridge({ setMcpIntegration: vi.fn().mockRejectedValue(new Error('Configuração inválida')) })
    page()
    fireEvent.click(screen.getByRole('tab', { name: 'Gemini' }))
    const toggle = screen.getByRole('switch', { name: 'RAGX no Gemini CLI' })
    await waitFor(() => expect(toggle).toBeEnabled())
    fireEvent.click(toggle)
    expect(await screen.findByRole('alert')).toHaveTextContent('Configuração inválida')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(bridge.setMcpIntegration).toHaveBeenCalledWith('gemini', true)
  })

  it('cliente ausente aparece sem conexão habilitada; verificar relê o estado', async () => {
    const bridge = installBridge()
    page()
    fireEvent.click(screen.getByRole('tab', { name: 'Outros agentes' }))
    await screen.findAllByText('Não detectado')
    expect(screen.getByRole('switch', { name: 'RAGX no Windsurf' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Verificar agentes' }))
    await waitFor(() => expect(bridge.getMcpIntegrations).toHaveBeenCalledTimes(2))
    expect(bridge.setMcpIntegration).not.toHaveBeenCalled()
  })

  it('o controle global do Claude fica na sua aba e preserva os perfis', () => {
    installBridge()
    const toggle = vi.fn()
    const claude = {
      enabled: true, busy: false, error: null, changed: false, toggle,
      profiles: [{ id: 'claude-code', name: 'padrão', label: 'Claude Code', dir: 'C:/u/.claude', enabled: true, hint: true, touch: true, nudge: true, added: false }],
      setProfile: vi.fn(), addProfile: vi.fn(), removeProfile: vi.fn(),
    }
    render(<ConnectionsPage connections={connectionChecks()} checking={false} onRefresh={vi.fn()} jobs={[]} claude={claude} />)
    expect(screen.queryByRole('switch', { name: 'RAGX no Claude Code' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Claude Code' }))
    fireEvent.click(screen.getByRole('switch', { name: 'RAGX no Claude Code' }))
    expect(toggle).toHaveBeenCalledOnce()
    expect(screen.getByRole('switch', { name: 'RAGX no perfil padrão' })).toBeInTheDocument()
  })

  it('onboarding apresenta e conecta Gemini com os mesmos controles', async () => {
    const bridge = installBridge()
    const clients = await bridge.getMcpIntegrations()
    bridge.setMcpIntegration = vi.fn().mockResolvedValue(clients.map((c) => c.id === 'gemini' ? { ...c, enabled: true } : c))
    render(<Onboarding connections={connectionChecks()} checking={false} onRefresh={vi.fn()} jobs={[]} onFinish={vi.fn()} />)
    expect(screen.getByText(/Claude Code, Codex, Gemini CLI, Cursor e Windsurf/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Gemini' }))
    const toggle = screen.getByRole('switch', { name: 'RAGX no Gemini CLI' })
    await waitFor(() => expect(toggle).toBeEnabled())
    fireEvent.click(toggle)
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'))
    expect(bridge.setMcpIntegration).toHaveBeenCalledWith('gemini', true)
  })
})

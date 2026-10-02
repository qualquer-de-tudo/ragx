import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { PreferencesPage } from '../PreferencesPage'
import { Toaster } from '../../components/ui/Toaster'
import { installBridge } from '../../test/snap'
import { resetToasts } from '../../toast'

afterEach(() => {
  cleanup()
  resetToasts()
  vi.restoreAllMocks()
})

describe('PreferencesPage', () => {
  it('as duas opções entram desligadas', async () => {
    installBridge()
    render(<PreferencesPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Preferências' })).toBeInTheDocument()
    const tray = await screen.findByRole('switch', { name: 'Ícone na bandeja do sistema' })
    await act(async () => {})
    expect(tray).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch', { name: 'Avisar quando um índice ficar defasado' })).toHaveAttribute('aria-checked', 'false')
  })

  it('reflete o que está salvo e liga pela ponte', async () => {
    const b = installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, notifyStale: true }) })
    render(<PreferencesPage />)
    const notify = await screen.findByRole('switch', { name: 'Avisar quando um índice ficar defasado' })
    await act(async () => {})
    expect(notify).toHaveAttribute('aria-checked', 'true')
    await act(async () => {
      fireEvent.click(screen.getByRole('switch', { name: 'Ícone na bandeja do sistema' }))
    })
    expect(b.setPreference).toHaveBeenCalledWith('tray', true)
    expect(screen.getByRole('switch', { name: 'Ícone na bandeja do sistema' })).toHaveAttribute('aria-checked', 'true')
  })

  it('falha ao salvar vira aviso e o interruptor não muda', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    installBridge({ setPreference: vi.fn().mockRejectedValue(new Error('disco cheio')) })
    render(
      <>
        <PreferencesPage />
        <Toaster />
      </>,
    )
    await act(async () => {})
    await act(async () => {
      fireEvent.click(screen.getByRole('switch', { name: 'Ícone na bandeja do sistema' }))
    })
    expect(screen.getByText(/Não foi possível salvar a preferência: disco cheio/)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Ícone na bandeja do sistema' })).toHaveAttribute('aria-checked', 'false')
  })
})

describe('PreferencesPage: Atualizações (RAGX-0192)', () => {
  const state = (over: Record<string, unknown> = {}) => ({ status: 'idle', currentVersion: '1.0.0-beta.5', version: null, progress: null, error: null, ...over })

  it('o aviso de assinatura aparece sempre, com a versão atual, e a atualização entra desligada', async () => {
    installBridge({ getUpdateState: vi.fn().mockResolvedValue(state()) })
    render(<PreferencesPage />)
    expect(screen.getByText(/O instalador não é assinado: o Windows pode mostrar o aviso do SmartScreen ao atualizar/)).toBeInTheDocument()
    expect(await screen.findByText(/Versão atual: 1\.0\.0-beta\.5/)).toBeInTheDocument()
    // ligada por padrão (v1.0.0): a pessoa não precisa ter mexido em nada
    await act(async () => {})
    expect(screen.getByRole('switch', { name: 'Verificar atualizações do painel' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: 'Verificar agora' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Instalar e reiniciar' })).not.toBeInTheDocument()
  })

  it('desligada pela pessoa: o interruptor fica desligado e "Verificar agora" desabilitado (nada de rede)', async () => {
    installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, autoUpdate: false }) })
    render(<PreferencesPage />)
    await act(async () => {})
    expect(screen.getByRole('switch', { name: 'Verificar atualizações do painel' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('button', { name: 'Verificar agora' })).toBeDisabled()
  })

  it('ligar grava a preferência; verificar agora chama a ponte quando ligada', async () => {
    const b = installBridge({ getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, autoUpdate: true }) })
    render(<PreferencesPage />)
    await act(async () => {})
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verificar agora' }))
    })
    expect(b.checkForUpdates).toHaveBeenCalledTimes(1)
    await act(async () => {
      fireEvent.click(screen.getByRole('switch', { name: 'Verificar atualizações do painel' }))
    })
    expect(b.setPreference).toHaveBeenCalledWith('autoUpdate', false)
  })

  it('"Instalar e reiniciar" só aparece com a atualização baixada; "Baixar" só com versão disponível', async () => {
    let push: (s: unknown) => void = () => {}
    const b = installBridge({
      getSettings: vi.fn().mockResolvedValue({ onboardingDone: true, autoUpdate: true }),
      onUpdate: vi.fn((cb: (s: never) => void) => {
        push = cb as (s: unknown) => void
        return () => {}
      }),
    })
    render(<PreferencesPage />)
    await act(async () => {})
    act(() => push(state({ status: 'available', version: '1.1.0' })))
    expect(screen.getByText(/versão 1\.1\.0 disponível/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Instalar e reiniciar' })).not.toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Baixar atualização' }))
    })
    expect(b.downloadUpdate).toHaveBeenCalled()
    act(() => push(state({ status: 'downloaded', version: '1.1.0', progress: 100 })))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Instalar e reiniciar' }))
    })
    expect(b.installUpdate).toHaveBeenCalledTimes(1)
  })

  it('erro da atualização aparece em português', async () => {
    installBridge({ getUpdateState: vi.fn().mockResolvedValue(state({ status: 'error', error: 'Não foi possível falar com o servidor de atualizações. Confira a conexão e tente de novo.' })) })
    render(<PreferencesPage />)
    expect(await screen.findByText(/Não foi possível falar com o servidor de atualizações/)).toBeInTheDocument()
  })
})

describe('PreferencesPage: Tema (RAGX-0193)', () => {
  it('o seletor reflete o tema, troca na hora e grava pela ponte', async () => {
    const b = installBridge()
    render(<PreferencesPage />)
    const group = screen.getByRole('radiogroup', { name: 'Tema' })
    expect(within(group).getAllByRole('radio').map((r) => r.textContent)).toEqual(['Escuro', 'Claro', 'Seguir o sistema'])
    expect(within(group).getByRole('radio', { name: 'Escuro' })).toHaveAttribute('aria-checked', 'true')
    await act(async () => {
      fireEvent.click(within(group).getByRole('radio', { name: 'Claro' }))
    })
    expect(b.setTheme).toHaveBeenCalledWith('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(within(group).getByRole('radio', { name: 'Claro' })).toHaveAttribute('aria-checked', 'true')
    await act(async () => {
      fireEvent.click(within(group).getByRole('radio', { name: 'Escuro' }))
    })
  })

  it('falha ao gravar volta ao tema anterior e avisa', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    installBridge({ setTheme: vi.fn().mockRejectedValue(new Error('disco cheio')) })
    render(
      <>
        <PreferencesPage />
        <Toaster />
      </>,
    )
    const group = screen.getByRole('radiogroup', { name: 'Tema' })
    await act(async () => {
      fireEvent.click(within(group).getByRole('radio', { name: 'Claro' }))
    })
    expect(screen.getByText(/Não foi possível salvar o tema: disco cheio/)).toBeInTheDocument()
    expect(within(group).getByRole('radio', { name: 'Escuro' })).toHaveAttribute('aria-checked', 'true')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})

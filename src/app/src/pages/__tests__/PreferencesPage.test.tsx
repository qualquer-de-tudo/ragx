import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
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

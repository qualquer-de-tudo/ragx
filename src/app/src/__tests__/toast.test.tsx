import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Toaster } from '../components/ui/Toaster'
import { DEDUPE_MS, MAX_VISIBLE, NOTICE_ERROR_MS, NOTICE_MS, notify, resetToasts } from '../toast'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
  resetToasts()
})
afterEach(() => {
  cleanup()
  resetToasts()
  vi.useRealTimers()
})

describe('Toaster', () => {
  it('a região viva está no DOM antes do primeiro aviso', () => {
    render(<Toaster />)
    expect(screen.getByRole('region', { name: 'Avisos' })).toHaveAttribute('aria-live', 'polite')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('erro é alert, sucesso e info são status', () => {
    render(<Toaster />)
    act(() => {
      notify.error('deu ruim')
      notify.success('deu bom')
      notify.info('fyi')
    })
    expect(screen.getByRole('alert')).toHaveTextContent('deu ruim')
    expect(screen.getAllByRole('status').map((n) => n.textContent)).toEqual(expect.arrayContaining([expect.stringContaining('deu bom'), expect.stringContaining('fyi')]))
  })

  it('no máximo 3 na tela: o 4º tira o mais antigo', () => {
    render(<Toaster />)
    act(() => {
      for (const t of ['a', 'b', 'c', 'd']) notify.info(t)
    })
    expect(MAX_VISIBLE).toBe(3)
    const texts = screen.getAllByRole('status').map((n) => n.textContent ?? '')
    expect(texts).toHaveLength(3)
    expect(texts.join('|')).not.toContain('a')
    expect(texts.join('|')).toContain('d')
  })

  it('o mesmo texto em 3 s não duplica; depois disso, sim', () => {
    render(<Toaster />)
    act(() => {
      notify.error('igual')
      notify.error('igual')
    })
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    act(() => {
      vi.advanceTimersByTime(DEDUPE_MS + 10)
      notify.error('igual')
    })
    expect(screen.getAllByRole('alert')).toHaveLength(2)
  })

  it('prazos: sucesso 4 s, erro 8 s', () => {
    render(<Toaster />)
    act(() => {
      notify.success('ok')
      notify.error('erro')
    })
    act(() => {
      vi.advanceTimersByTime(NOTICE_MS - 100)
    })
    expect(screen.getByText('ok')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(screen.queryByText('ok')).not.toBeInTheDocument()
    expect(screen.getByText('erro')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(NOTICE_ERROR_MS - NOTICE_MS)
    })
    expect(screen.queryByText('erro')).not.toBeInTheDocument()
  })

  it('com o ponteiro em cima o prazo não corre, e retoma de onde parou', () => {
    render(<Toaster />)
    act(() => {
      notify.success('parado')
    })
    const toast = screen.getByRole('status')
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    fireEvent.mouseEnter(toast)
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getByText('parado')).toBeInTheDocument()
    fireEvent.mouseLeave(toast)
    act(() => {
      vi.advanceTimersByTime(900)
    })
    expect(screen.getByText('parado')).toBeInTheDocument() // faltavam 1000 ms
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(screen.queryByText('parado')).not.toBeInTheDocument()
  })

  it('o foco também pausa; "Fechar aviso" tira na hora', () => {
    render(<Toaster />)
    act(() => {
      notify.error('fixo')
    })
    const close = screen.getByRole('button', { name: 'Fechar aviso' })
    act(() => close.focus())
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getByText('fixo')).toBeInTheDocument()
    fireEvent.click(close)
    expect(screen.queryByText('fixo')).not.toBeInTheDocument()
  })
})

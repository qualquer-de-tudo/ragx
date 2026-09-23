import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { ConfirmButton } from '../ConfirmButton'

function renderButton(over: { disabled?: boolean } = {}) {
  const onConfirm = vi.fn()
  const utils = render(
    <ConfirmButton
      label="Reindexar do zero"
      confirmLabel="Confirmar reindexação"
      onConfirm={onConfirm}
      tone="critical"
      disabled={over.disabled}
    />,
  )
  return { ...utils, onConfirm }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ConfirmButton', () => {
  it('o primeiro clique não confirma: só troca o texto', () => {
    const { onConfirm } = renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Reindexar do zero' }))
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Confirmar reindexação' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Clique de novo para confirmar.')
  })

  it('o segundo clique confirma uma vez e volta ao texto normal', () => {
    const { onConfirm } = renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Reindexar do zero' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar reindexação' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Reindexar do zero' })).toBeInTheDocument()
  })

  it('volta ao normal depois de 5 s sem o segundo clique', () => {
    const { onConfirm } = renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Reindexar do zero' }))
    act(() => {
      vi.advanceTimersByTime(4900)
    })
    expect(screen.getByRole('button', { name: 'Confirmar reindexação' })).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(screen.getByRole('button', { name: 'Reindexar do zero' })).toBeInTheDocument()
    // Clique depois do prazo é um primeiro clique de novo.
    fireEvent.click(screen.getByRole('button', { name: 'Reindexar do zero' }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('Esc cancela a confirmação', () => {
    const { onConfirm } = renderButton()
    const button = screen.getByRole('button', { name: 'Reindexar do zero' })
    fireEvent.click(button)
    fireEvent.keyDown(button, { key: 'Escape' })
    expect(screen.getByRole('button', { name: 'Reindexar do zero' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reindexar do zero' }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('desabilitado não arma nem confirma', () => {
    const { onConfirm } = renderButton({ disabled: true })
    const button = screen.getByRole('button', { name: 'Reindexar do zero' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    fireEvent.click(button)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

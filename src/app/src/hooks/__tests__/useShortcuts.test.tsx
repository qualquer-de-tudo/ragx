import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { useShortcuts } from '../useShortcuts'

afterEach(cleanup)

function Host({ enabled = true, onAction }: { enabled?: boolean; onAction: (a: unknown) => void }) {
  useShortcuts(enabled, onAction)
  return (
    <>
      <input aria-label="campo" />
      <textarea aria-label="area" />
      <div contentEditable suppressContentEditableWarning aria-label="editavel" />
      <button>botao</button>
    </>
  )
}

describe('useShortcuts', () => {
  it('Ctrl+K e Meta+K disparam a paleta e cancelam o comportamento padrão', () => {
    const onAction = vi.fn()
    render(<Host onAction={onAction} />)
    const ev = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true, cancelable: true })
    window.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(onAction).toHaveBeenCalledTimes(2)
    expect(onAction).toHaveBeenLastCalledWith({ type: 'palette' })
  })

  it('/ e ? não disparam com foco em input, textarea ou contenteditable; Ctrl+K dispara mesmo assim', () => {
    const onAction = vi.fn()
    const { getByLabelText } = render(<Host onAction={onAction} />)
    for (const label of ['campo', 'area']) {
      const el = getByLabelText(label)
      el.focus()
      fireEvent.keyDown(el, { key: '/' })
      fireEvent.keyDown(el, { key: '?' })
    }
    const editable = getByLabelText('editavel')
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    fireEvent.keyDown(editable, { key: '/' })
    expect(onAction).not.toHaveBeenCalled()
    fireEvent.keyDown(getByLabelText('campo'), { key: 'k', ctrlKey: true })
    expect(onAction).toHaveBeenCalledWith({ type: 'palette' })
  })

  it('/ e ? funcionam com o foco num botão', () => {
    const onAction = vi.fn()
    const { getByText } = render(<Host onAction={onAction} />)
    fireEvent.keyDown(getByText('botao'), { key: '/' })
    fireEvent.keyDown(getByText('botao'), { key: '?' })
    expect(onAction.mock.calls.map((c) => (c[0] as { type: string }).type)).toEqual(['search', 'help'])
  })

  it('desabilitado (onboarding) não escuta; e o ouvinte sai ao desmontar', () => {
    const off = vi.fn()
    const { unmount: unmountOff } = render(<Host enabled={false} onAction={off} />)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(off).not.toHaveBeenCalled()
    unmountOff()

    const on = vi.fn()
    const { unmount } = render(<Host onAction={on} />)
    unmount()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(on).not.toHaveBeenCalled()
  })
})

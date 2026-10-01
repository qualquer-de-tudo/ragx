import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { IconButton } from './IconButton'

const FOCUSABLE = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'a[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusablesIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE))
}

/**
 * Janela modal: foco preso dentro dela enquanto aberta, Esc e clique fora fecham, e o foco volta para quem abriu.
 * O primeiro foco vai para o elemento com `data-autofocus` ou, sem ele, para o primeiro focável.
 */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const root = ref.current
    if (root) {
      const first = root.querySelector<HTMLElement>('[data-autofocus]') ?? focusablesIn(root)[0] ?? root
      first.focus()
    }
    return () => {
      if (opener?.isConnected) opener.focus()
    }
  }, [])

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
      return
    }
    if (e.key !== 'Tab' || !ref.current) return
    const items = focusablesIn(ref.current)
    if (items.length === 0) {
      e.preventDefault()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement
    const inside = active instanceof Node && ref.current.contains(active)
    if (e.shiftKey && (active === first || !inside || active === ref.current)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && (active === last || !inside)) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <header className="modal-head">
          <h2 className="modal-title" id={titleId}>
            {title}
          </h2>
          <IconButton label="Fechar" icon="close" onClick={onClose} />
        </header>
        {children}
      </div>
    </div>
  )
}

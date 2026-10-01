import { useEffect, useId, useState, type FocusEvent, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

const SHOW_DELAY_MS = 400
const MAX_WIDTH = 320
const GAP = 6
const EDGE = 8

/** O que o gatilho recebe para virar âncora do tooltip: espalhe no elemento (`{...props}`). */
export interface TooltipTriggerProps {
  'aria-describedby'?: string
  tabIndex?: number
  onMouseEnter: (e: MouseEvent<HTMLElement>) => void
  onMouseLeave: () => void
  onFocus: (e: FocusEvent<HTMLElement>) => void
  onBlur: () => void
  onKeyDown: (e: KeyboardEvent<HTMLElement>) => void
}

/**
 * Dica de texto (RAGX-0179), no lugar do atributo `title`, que teclado e toque não alcançam. Abre com o mouse (depois
 * de um instante) e na hora com o foco, fecha com Esc, mouse saindo ou foco saindo, e liga ao gatilho por
 * `aria-describedby`. Sem biblioteca: a posição é calculada ao abrir (`position: fixed`), então não é cortada pelo
 * `overflow: hidden` de quem trunca o texto, e o balão vai para o `body` por portal.
 *
 * Sem wrapper: `children` recebe as props do gatilho e devolve o elemento. `focusable` põe `tabIndex={0}` para texto
 * que não é focável (caminho truncado, selo, hora).
 */
export function Tooltip({
  text,
  focusable = false,
  children,
}: {
  text: string
  focusable?: boolean
  children: (props: TooltipTriggerProps) => ReactNode
}) {
  const id = useId()
  // Sem refs: o atraso do mouse é um efeito sobre `pending`, que se limpa sozinho ao sair, trocar ou desmontar.
  const [pending, setPending] = useState<HTMLElement | null>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)

  const place = (el: HTMLElement) => {
    const r = el.getBoundingClientRect()
    const left = Math.max(EDGE, Math.min(r.left, window.innerWidth - MAX_WIDTH - EDGE))
    setPos({ left, top: r.bottom + GAP })
  }
  const close = () => {
    setPending(null)
    setPos(null)
  }

  useEffect(() => {
    if (pending === null) return
    const t = setTimeout(() => {
      const r = pending.getBoundingClientRect()
      const left = Math.max(EDGE, Math.min(r.left, window.innerWidth - MAX_WIDTH - EDGE))
      setPos({ left, top: r.bottom + GAP })
      setPending(null)
    }, SHOW_DELAY_MS)
    return () => clearTimeout(t)
  }, [pending])

  const props: TooltipTriggerProps = {
    'aria-describedby': pos ? id : undefined,
    tabIndex: focusable ? 0 : undefined,
    onMouseEnter: (e) => setPending(e.currentTarget),
    onMouseLeave: close,
    onFocus: (e) => {
      setPending(null)
      place(e.currentTarget)
    },
    onBlur: close,
    onKeyDown: (e) => {
      if (e.key === 'Escape' && pos) {
        e.stopPropagation()
        close()
      }
    },
  }

  return (
    <>
      {children(props)}
      {pos &&
        createPortal(
          <span role="tooltip" id={id} className="tooltip" style={{ left: pos.left, top: pos.top }}>
            {text}
          </span>,
          document.body,
        )}
    </>
  )
}

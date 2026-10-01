import type { ReactNode } from 'react'

/**
 * Tela ou lista vazia, anunciada como estado (`role="status"`). `className` troca o visual (a base é `.empty`):
 * `dim` deixa só o texto de apoio, sem o respiro de 24 px.
 */
export function EmptyState({
  title,
  children,
  action,
  className = 'empty',
}: {
  title?: string
  children: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={className} role="status">
      {title && <p className="empty-title">{title}</p>}
      <p>{children}</p>
      {action}
    </div>
  )
}

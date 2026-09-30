import { useId, type ReactNode } from 'react'

/** Card com título que também nomeia a região (`aria-labelledby`), para leitor de tela e testes. */
export function Section({ title, className, children }: { title: string; className?: string; children: ReactNode }) {
  const titleId = useId()
  return (
    <section className={`card detail-card${className ? ` ${className}` : ''}`} aria-labelledby={titleId}>
      <h2 className="card-title" id={titleId}>
        {title}
      </h2>
      {children}
    </section>
  )
}

export function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  )
}

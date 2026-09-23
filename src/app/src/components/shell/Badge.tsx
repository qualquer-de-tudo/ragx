import type { ReactNode } from 'react'

export type Tone = 'good' | 'warning' | 'critical' | 'accent' | 'muted'

/**
 * Selo "● Texto". O ponto é decorativo (`aria-hidden`); o texto é obrigatório,
 * porque cor sozinha não diz o estado para quem não distingue as cores.
 */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span aria-hidden="true">●</span> <span className="badge-text">{children}</span>
    </span>
  )
}

import { MARK_FULL, MARK_SMALL, MARK_VIEWBOX } from './markPaths'

/**
 * Símbolo do RAGX: um X com abertura em losango no cruzamento (o foco) e um
 * núcleo no centro (o trecho recuperado). Abaixo de 32 px o núcleo some e as
 * barras engrossam (desenho "small"), senão a abertura fecha e vira borrão.
 * Geometria gerada por scripts/brand.py, a mesma dos ícones do .exe.
 */
export function RagxMark({ size = 24, className }: { size?: number; className?: string }) {
  const mark = size < 32 ? MARK_SMALL : MARK_FULL
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={MARK_VIEWBOX}
      aria-hidden="true"
      focusable="false"
    >
      <path fill="var(--accent)" d={mark.body} />
      {mark.core && <path fill="var(--ink)" d={mark.core} />}
    </svg>
  )
}

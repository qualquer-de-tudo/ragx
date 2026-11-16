import { MARK_FULL, MARK_SMALL, MARK_TINY, MARK_VIEWBOX } from './markPaths'

/**
 * Símbolo do RAGX (identidade Grafo, ADR-0017): quatro nós ligados por arestas a um anel, o índice. É o único lugar
 * da interface com as cores da marca (`--brand-node`, `--brand-ring`); o resto é preto e branco. O desenho muda com
 * o tamanho, como nos ícones do .exe: até 20 px as diagonais se cruzam e o anel vira ponto; até 40 px tudo engrossa.
 * Geometria gerada por scripts/brand.py.
 */
export function RagxMark({ size = 24, className }: { size?: number; className?: string }) {
  const mark = size <= 20 ? MARK_TINY : size <= 40 ? MARK_SMALL : MARK_FULL
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={MARK_VIEWBOX}
      aria-hidden="true"
      focusable="false"
    >
      {mark.edges.map(([x1, y1, x2, y2]) => (
        <line
          key={`${x1}-${y1}`}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke="var(--brand-node)"
          strokeWidth={mark.edge}
          strokeLinecap="round"
        />
      ))}
      {mark.nodes.map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={mark.node} fill="var(--brand-node)" />
      ))}
      {mark.ring > 0 && (
        <circle cx={32} cy={32} r={mark.ring} fill="none" stroke="var(--brand-ring)" strokeWidth={mark.ringWidth} />
      )}
      {mark.dot > 0 && <circle cx={32} cy={32} r={mark.dot} fill="var(--brand-ring)" />}
    </svg>
  )
}

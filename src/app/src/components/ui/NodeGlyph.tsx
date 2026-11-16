/** Os cinco estados que a forma do nó carrega (identidade Grafo, ADR-0017). São os mesmos tons do `Badge`. */
export type NodeState = 'good' | 'warning' | 'critical' | 'accent' | 'muted'

/**
 * Glifo de estado: a forma do nó diz o estado e a cor só confirma. Cheio com anel (em dia), meio cheio (defasado),
 * cortado (com problema), anel tracejado com ponto em órbita (em andamento; gira devagar, parado com
 * `prefers-reduced-motion`) e vazio (sem uso). Sempre decorativo: quem usa põe o estado em texto ao lado.
 * A cor vem do CSS (`.node-glyph-<estado>`, por `currentColor`).
 */
export function NodeGlyph({ state, size = 14, className }: { state: NodeState; size?: number; className?: string }) {
  return (
    <svg
      className={`node-glyph node-glyph-${state}${className ? ` ${className}` : ''}`}
      data-state={state}
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      {state === 'good' && (
        <>
          <circle cx="9" cy="9" r="7.5" strokeWidth="1.5" strokeOpacity="0.45" />
          <circle cx="9" cy="9" r="4.5" fill="currentColor" stroke="none" />
        </>
      )}
      {state === 'warning' && (
        <>
          <circle cx="9" cy="9" r="6" strokeWidth="2" />
          <path d="M9 3 A6 6 0 0 0 9 15 Z" fill="currentColor" stroke="none" />
        </>
      )}
      {state === 'critical' && (
        <>
          <circle cx="9" cy="9" r="6" strokeWidth="2" />
          <line x1="4.5" y1="13.5" x2="13.5" y2="4.5" strokeWidth="2" />
        </>
      )}
      {state === 'accent' && (
        <>
          <circle className="node-glyph-orbit" cx="9" cy="9" r="7" strokeWidth="1.5" strokeDasharray="3 2.5" />
          <circle cx="9" cy="9" r="2.5" fill="currentColor" stroke="none" />
        </>
      )}
      {state === 'muted' && <circle cx="9" cy="9" r="6" strokeWidth="2" />}
    </svg>
  )
}

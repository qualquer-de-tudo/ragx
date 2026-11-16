import type { ReactNode } from 'react'
import { NodeGlyph, type NodeState } from '../ui/NodeGlyph'

export type Tone = NodeState

/**
 * Selo de estado na linguagem Grafo (ADR-0017): glifo do nó + aresta curta + rótulo em mono caixa-alta. A forma do nó
 * diz o estado (cheio, meio, cortado, em órbita, vazio) e o glifo é decorativo (`aria-hidden`); o texto é
 * obrigatório, porque cor sozinha não diz o estado para quem não distingue as cores.
 */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-mark" aria-hidden="true">
        <NodeGlyph state={tone} />
        <span className="badge-edge" />
      </span>
      <span className="badge-text">{children}</span>
    </span>
  )
}

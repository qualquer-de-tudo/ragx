/**
 * Grafo em SVG, com layout dirigido por forças escrito aqui mesmo.
 *
 * Por que não uma biblioteca: cytoscape e d3 pesam centenas de KB e trazem um
 * modelo de dados próprio. O que este painel precisa é desenhar algumas dezenas
 * de nós — o teto é `maxVisibleNodes`, e acima disso o grafo vira ruído de
 * qualquer jeito. Cem linhas resolvem, ficam legíveis e não entram no bundle
 * como dependência que ninguém revisa.
 *
 * A simulação roda em passos limitados dentro de um efeito e para sozinha. Sem
 * `requestAnimationFrame` infinito: um painel escondido não pode continuar
 * queimando CPU.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { GraphEdge, GraphNode, GraphSlice } from '../../../src/rag/types';

interface Pos {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const PASSOS = 220;
const RAIO = 5;

export function GraphView({
  graph,
  center,
  onSelect,
  onExpand,
  selectedId,
  height = 360,
}: {
  graph: GraphSlice;
  center?: string;
  onSelect?: (n: GraphNode) => void;
  onExpand?: (n: GraphNode) => void;
  selectedId?: string;
  height?: number;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const arrastando = useRef<{ x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const largura = 600;
  const altura = height;

  const posicoes = useMemo(
    () => layout(graph.nodes, graph.edges, largura, altura, center),
    [graph.nodes, graph.edges, largura, altura, center],
  );

  const porId = useMemo(() => new Map(posicoes.map((p) => [p.id, p])), [posicoes]);

  // Teclado: zoom e reset sem mouse (§42).
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '+' || e.key === '=') setZoom((z) => Math.min(3, z * 1.2));
      if (e.key === '-') setZoom((z) => Math.max(0.4, z / 1.2));
      if (e.key === '0') {
        setZoom(1);
        setPan({ x: 0, y: 0 });
      }
    };
    el.addEventListener('keydown', onKey);
    return () => el.removeEventListener('keydown', onKey);
  }, []);

  if (!graph.nodes.length) {
    return (
      <div className="p-6 text-center text-fg-muted border border-border rounded">
        <p className="font-semibold text-fg mb-1">Sem dados de grafo</p>
        <p className="text-[0.95em]">Selecione uma entidade para explorar as relações.</p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded overflow-hidden">
      <div className="flex items-center gap-2 px-2 py-1 border-b border-border text-[0.85em]">
        <span className="text-fg-muted">
          {graph.nodes.length} nós · {graph.edges.length} relações
        </span>
        {graph.truncated && (
          // Dizer que cortou é obrigatório: um grafo truncado em silêncio faz
          // a pessoa concluir que a relação não existe.
          <span className="text-warn" title="Aumente ragx.maxVisibleNodes para ver mais">
            · truncado
          </span>
        )}
        <div className="ml-auto flex gap-1">
          <button
            type="button"
            aria-label="Aproximar"
            onClick={() => setZoom((z) => Math.min(3, z * 1.2))}
            className="px-1.5 hover:bg-hover rounded"
          >
            +
          </button>
          <button
            type="button"
            aria-label="Afastar"
            onClick={() => setZoom((z) => Math.max(0.4, z / 1.2))}
            className="px-1.5 hover:bg-hover rounded"
          >
            −
          </button>
          <button
            type="button"
            aria-label="Centralizar"
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
            className="px-1.5 hover:bg-hover rounded"
          >
            ⌂
          </button>
        </div>
      </div>

      <svg
        ref={svgRef}
        role="img"
        aria-label={`Grafo com ${graph.nodes.length} entidades`}
        tabIndex={0}
        width="100%"
        height={altura}
        viewBox={`0 0 ${largura} ${altura}`}
        className="bg-bg cursor-grab active:cursor-grabbing outline-none"
        onMouseDown={(e) => (arrastando.current = { x: e.clientX - pan.x, y: e.clientY - pan.y })}
        onMouseMove={(e) => {
          if (!arrastando.current) return;
          setPan({ x: e.clientX - arrastando.current.x, y: e.clientY - arrastando.current.y });
        }}
        onMouseUp={() => (arrastando.current = null)}
        onMouseLeave={() => (arrastando.current = null)}
      >
        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          {graph.edges.map((e, i) => {
            const a = porId.get(e.source);
            const b = porId.get(e.target);
            if (!a || !b) return null;
            return (
              <g key={`${e.source}-${e.target}-${i}`}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="var(--vscode-panel-border)"
                  strokeWidth={1}
                />
                <text
                  x={(a.x + b.x) / 2}
                  y={(a.y + b.y) / 2 - 2}
                  textAnchor="middle"
                  fontSize={7}
                  fill="var(--vscode-descriptionForeground)"
                >
                  {e.type}
                </text>
              </g>
            );
          })}

          {graph.nodes.map((n) => {
            const p = porId.get(n.id);
            if (!p) return null;
            const selecionado = n.id === selectedId;
            const ehCentro = n.id === center;
            return (
              <g
                key={n.id}
                transform={`translate(${p.x} ${p.y})`}
                className="cursor-pointer"
                onClick={() => onSelect?.(n)}
                onDoubleClick={() => onExpand?.(n)}
              >
                <title>
                  {n.name} ({n.type})
                  {n.expanded === false ? ' — duplo clique para expandir' : ''}
                </title>
                <circle
                  r={ehCentro ? RAIO + 2 : RAIO}
                  fill={
                    selecionado || ehCentro
                      ? 'var(--vscode-textLink-foreground)'
                      : 'var(--vscode-badge-background)'
                  }
                  stroke={
                    selecionado
                      ? 'var(--vscode-focusBorder)'
                      : 'var(--vscode-panel-border)'
                  }
                  strokeWidth={selecionado ? 2 : 1}
                />
                {/* Anel tracejado = tem vizinho não carregado. É o convite à
                    expansão progressiva, em vez de carregar tudo (§12). */}
                {n.expanded === false && (
                  <circle
                    r={RAIO + 3}
                    fill="none"
                    stroke="var(--vscode-descriptionForeground)"
                    strokeDasharray="2 2"
                    strokeWidth={1}
                  />
                )}
                <text
                  y={-RAIO - 5}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--vscode-foreground)"
                >
                  {n.name.length > 22 ? n.name.slice(0, 21) + '…' : n.name}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <p className="px-2 py-1 border-t border-border text-[0.8em] text-fg-muted">
        Clique seleciona · duplo clique expande · arraste move · <kbd>+</kbd>{' '}
        <kbd>−</kbd> <kbd>0</kbd>
      </p>
    </div>
  );
}

/**
 * Layout dirigido por forças, determinístico.
 *
 * Posição inicial vem de um hash do id, não de `Math.random()`: sem isso o
 * mesmo grafo sai diferente a cada render e a pessoa perde a referência visual
 * que acabou de construir.
 */
function layout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  largura: number,
  altura: number,
  center?: string,
): Pos[] {
  const cx = largura / 2;
  const cy = altura / 2;

  const pos: Pos[] = nodes.map((n, i) => {
    if (n.id === center) return { id: n.id, x: cx, y: cy, vx: 0, vy: 0 };
    const angulo = (hash(n.id) % 360) * (Math.PI / 180);
    const raio = 60 + (i % 5) * 28;
    return {
      id: n.id,
      x: cx + Math.cos(angulo) * raio,
      y: cy + Math.sin(angulo) * raio,
      vx: 0,
      vy: 0,
    };
  });

  const indice = new Map(pos.map((p, i) => [p.id, i]));
  const ligacoes = edges
    .map((e) => [indice.get(e.source), indice.get(e.target)] as const)
    .filter((p): p is readonly [number, number] => p[0] !== undefined && p[1] !== undefined);

  for (let passo = 0; passo < PASSOS; passo++) {
    const resfriamento = 1 - passo / PASSOS;

    // Repulsão entre todos os pares. O(n²) é aceitável porque n tem teto.
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const a = pos[i];
        const b = pos[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) {
          // Nós exatamente sobrepostos: desempata de forma estável.
          dx = ((hash(a.id + b.id) % 10) - 5) / 10 || 0.5;
          dy = ((hash(b.id + a.id) % 10) - 5) / 10 || 0.5;
          d2 = dx * dx + dy * dy;
        }
        const forca = 900 / d2;
        const d = Math.sqrt(d2);
        a.vx -= (dx / d) * forca;
        a.vy -= (dy / d) * forca;
        b.vx += (dx / d) * forca;
        b.vy += (dy / d) * forca;
      }
    }

    // Atração pelas arestas.
    for (const [i, j] of ligacoes) {
      const a = pos[i];
      const b = pos[j];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const forca = (d - 90) * 0.02;
      a.vx += (dx / d) * forca;
      a.vy += (dy / d) * forca;
      b.vx -= (dx / d) * forca;
      b.vy -= (dy / d) * forca;
    }

    for (const p of pos) {
      if (p.id === center) {
        // O centro fica parado: é a âncora da leitura.
        p.vx = 0;
        p.vy = 0;
        continue;
      }
      p.vx += (cx - p.x) * 0.002;
      p.vy += (cy - p.y) * 0.002;
      p.x += Math.max(-12, Math.min(12, p.vx)) * resfriamento;
      p.y += Math.max(-12, Math.min(12, p.vy)) * resfriamento;
      p.vx *= 0.82;
      p.vy *= 0.82;
      p.x = Math.max(24, Math.min(largura - 24, p.x));
      p.y = Math.max(20, Math.min(altura - 16, p.y));
    }
  }
  return pos;
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

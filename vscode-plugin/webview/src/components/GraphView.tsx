/**
 * Grafo em SVG, com layout dirigido por forças escrito aqui mesmo.
 *
 * Por que não uma biblioteca: cytoscape e d3 pesam centenas de KB e trazem um
 * modelo de dados próprio. O que este painel precisa é desenhar algumas dezenas
 * de nós — o teto é `maxVisibleNodes`, e acima disso o grafo vira ruído de
 * qualquer jeito. Isto resolve, fica legível e não entra no bundle como
 * dependência que ninguém revisa.
 *
 * A simulação roda em passos limitados dentro de um `useMemo` e para sozinha.
 * Sem `requestAnimationFrame` infinito: um painel escondido não pode continuar
 * queimando CPU.
 *
 * Três decisões existem porque a versão anterior virava emaranhado:
 *
 *   1. **O tamanho do desenho é medido, não fixo.** O `viewBox` era 600×360
 *      sempre; na aba do editor o grafo aparecia esticado e minúsculo.
 *   2. **Rótulo de aresta só quando dá para ler.** Escrever o tipo em todas as
 *      arestas de um grafo com 80 nós produz uma mancha de texto sobreposto.
 *   3. **Foco escurece o resto.** Com muitos nós, saber quem se liga a quem
 *      exige apagar o que não se liga.
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

const PASSOS = 260;

/**
 * Cor por tipo de entidade.
 *
 * Os tokens `charts-*` do VS Code existem justamente para isto e acompanham o
 * tema da pessoa. O fallback só entra em tema que não os define.
 */
const CORES: Record<string, string> = {
  class: 'var(--vscode-charts-blue, #4e94ce)',
  function: 'var(--vscode-charts-green, #89d185)',
  method: 'var(--vscode-charts-green, #89d185)',
  module: 'var(--vscode-charts-purple, #b180d7)',
  file: 'var(--vscode-charts-purple, #b180d7)',
  service: 'var(--vscode-charts-orange, #d18616)',
  concept: 'var(--vscode-charts-yellow, #cca700)',
  entity: 'var(--vscode-charts-foreground, #cccccc)',
};

function corDe(tipo: string): string {
  return CORES[tipo] ?? CORES.entity;
}

/** Conhecimento base vem de fora do repositório — e precisa ser visível. */
function ehBase(n: GraphNode): boolean {
  return Boolean(n.documentPath?.startsWith('@base/'));
}

export function GraphView({
  graph,
  center,
  onSelect,
  onExpand,
  onOpen,
  selectedId,
  height = 360,
}: {
  graph: GraphSlice;
  center?: string;
  onSelect?: (n: GraphNode) => void;
  onExpand?: (n: GraphNode) => void;
  onOpen?: (n: GraphNode) => void;
  selectedId?: string;
  height?: number;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hover, setHover] = useState<string | undefined>();
  const [tiposOcultos, setTiposOcultos] = useState<Set<string>>(new Set());
  const [rotulos, setRotulos] = useState(true);
  const arrastando = useRef<{ x: number; y: number } | null>(null);
  const moveu = useRef(false);
  const caixa = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // A largura real do container, não um número fixo. Sem isto o mesmo grafo
  // sai apertado na barra lateral e esticado na aba do editor.
  const [largura, setLargura] = useState(600);
  useEffect(() => {
    const el = caixa.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entrada]) => {
      const w = Math.round(entrada.contentRect.width);
      if (w > 0) setLargura(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const tipos = useMemo(() => {
    const contagem = new Map<string, number>();
    for (const n of graph.nodes) contagem.set(n.type, (contagem.get(n.type) ?? 0) + 1);
    return [...contagem.entries()].sort((a, b) => b[1] - a[1]);
  }, [graph.nodes]);

  const visivel = useMemo(() => {
    const nodes = graph.nodes.filter((n) => !tiposOcultos.has(n.type));
    const ids = new Set(nodes.map((n) => n.id));
    return {
      nodes,
      edges: graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
      truncated: graph.truncated,
    } satisfies GraphSlice;
  }, [graph, tiposOcultos]);

  /** Grau real, do que está desenhado. Vira o tamanho do círculo. */
  const graus = useMemo(() => {
    const g = new Map<string, number>();
    for (const e of visivel.edges) {
      g.set(e.source, (g.get(e.source) ?? 0) + 1);
      g.set(e.target, (g.get(e.target) ?? 0) + 1);
    }
    return g;
  }, [visivel.edges]);

  const altura = height;
  const posicoes = useMemo(
    () => layout(visivel.nodes, visivel.edges, largura, altura, center),
    [visivel.nodes, visivel.edges, largura, altura, center],
  );
  const porId = useMemo(() => new Map(posicoes.map((p) => [p.id, p])), [posicoes]);

  /** Quem está ligado ao nó em foco — o resto escurece. */
  const foco = hover ?? selectedId;
  const vizinhos = useMemo(() => {
    if (!foco) return undefined;
    const set = new Set<string>([foco]);
    for (const e of visivel.edges) {
      if (e.source === foco) set.add(e.target);
      if (e.target === foco) set.add(e.source);
    }
    return set;
  }, [foco, visivel.edges]);

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

  // Com muitos nós, o nome de cada aresta vira mancha. O limite é sobre o que
  // dá para LER, não sobre o que dá para desenhar.
  const mostrarTipoAresta = rotulos && visivel.edges.length <= 28;
  const mostrarNome = (id: string) =>
    rotulos && (visivel.nodes.length <= 45 || id === foco || id === center || id === selectedId);

  return (
    <div ref={caixa} className="border border-border rounded overflow-hidden">
      <div className="flex items-center gap-2 px-2 py-1 border-b border-border text-[0.85em] flex-wrap">
        <span className="text-fg-muted">
          {visivel.nodes.length} nós · {visivel.edges.length} relações
          {tiposOcultos.size > 0 && ` · ${graph.nodes.length - visivel.nodes.length} ocultos`}
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
            aria-label={rotulos ? 'Ocultar rótulos' : 'Mostrar rótulos'}
            title={rotulos ? 'Ocultar rótulos' : 'Mostrar rótulos'}
            aria-pressed={rotulos}
            onClick={() => setRotulos(!rotulos)}
            className={`px-1.5 rounded hover:bg-hover ${rotulos ? '' : 'text-fg-muted'}`}
          >
            Aa
          </button>
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
            title="Centralizar e restaurar o zoom"
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

      {/* Legenda que também FILTRA: ver "só as classes" é a pergunta mais
          frequente sobre um grafo, e escondê-la num menu não ajuda ninguém. */}
      {tipos.length > 1 && (
        <div className="flex items-center gap-1 flex-wrap px-2 py-1 border-b border-border">
          {tipos.map(([tipo, n]) => {
            const oculto = tiposOcultos.has(tipo);
            return (
              <button
                key={tipo}
                type="button"
                aria-pressed={!oculto}
                title={oculto ? `Mostrar ${tipo}` : `Ocultar ${tipo}`}
                onClick={() =>
                  setTiposOcultos((atual) => {
                    const novo = new Set(atual);
                    oculto ? novo.delete(tipo) : novo.add(tipo);
                    return novo;
                  })
                }
                className={`inline-flex items-center gap-1 px-1.5 py-[1px] rounded text-[0.8em]
                            hover:bg-hover ${oculto ? 'opacity-40 line-through' : ''}`}
              >
                <span
                  aria-hidden
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ background: corDe(tipo) }}
                />
                {tipo} <span className="text-fg-muted">{n}</span>
              </button>
            );
          })}
        </div>
      )}

      <svg
        ref={svgRef}
        role="img"
        aria-label={`Grafo com ${visivel.nodes.length} entidades e ${visivel.edges.length} relações`}
        tabIndex={0}
        width="100%"
        height={altura}
        viewBox={`0 0 ${largura} ${altura}`}
        className="bg-bg cursor-grab active:cursor-grabbing outline-none"
        onMouseDown={(e) => {
          arrastando.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
          moveu.current = false;
        }}
        onMouseMove={(e) => {
          if (!arrastando.current) return;
          moveu.current = true;
          setPan({ x: e.clientX - arrastando.current.x, y: e.clientY - arrastando.current.y });
        }}
        onMouseUp={() => (arrastando.current = null)}
        onMouseLeave={() => {
          arrastando.current = null;
          setHover(undefined);
        }}
      >
        <defs>
          {/* A seta diz a DIREÇÃO da relação. Sem ela, "A chama B" e "B chama
              A" desenham a mesma linha e o grafo perde metade do sentido. */}
          <marker
            id="ragx-seta"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--vscode-panel-border)" />
          </marker>
        </defs>

        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          {visivel.edges.map((e, i) => {
            const a = porId.get(e.source);
            const b = porId.get(e.target);
            if (!a || !b) return null;
            const ativa = !vizinhos || (vizinhos.has(e.source) && vizinhos.has(e.target));
            // Encolhe a linha no destino para a seta não entrar no círculo.
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const d = Math.hypot(dx, dy) || 1;
            const r = raioDe(graus.get(e.target) ?? 0) + 4;
            const fx = b.x - (dx / d) * r;
            const fy = b.y - (dy / d) * r;
            return (
              <g key={`${e.source}-${e.target}-${i}`} opacity={ativa ? 1 : 0.12}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={fx}
                  y2={fy}
                  stroke="var(--vscode-panel-border)"
                  strokeWidth={ativa && vizinhos ? 1.6 : 1}
                  markerEnd="url(#ragx-seta)"
                />
                {(mostrarTipoAresta || (vizinhos && ativa)) && (
                  <text
                    x={(a.x + b.x) / 2}
                    y={(a.y + b.y) / 2 - 3}
                    textAnchor="middle"
                    fontSize={8}
                    fill="var(--vscode-descriptionForeground)"
                  >
                    {e.type}
                  </text>
                )}
              </g>
            );
          })}

          {visivel.nodes.map((n) => {
            const p = porId.get(n.id);
            if (!p) return null;
            const selecionado = n.id === selectedId;
            const ehCentro = n.id === center;
            const aceso = !vizinhos || vizinhos.has(n.id);
            const grau = graus.get(n.id) ?? 0;
            const raio = raioDe(grau) + (ehCentro ? 2 : 0);
            return (
              <g
                key={n.id}
                transform={`translate(${p.x} ${p.y})`}
                opacity={aceso ? 1 : 0.15}
                className="cursor-pointer"
                onMouseEnter={() => setHover(n.id)}
                onClick={() => {
                  // Arrastar o fundo não pode selecionar o nó que ficou sob o
                  // cursor no fim do movimento.
                  if (!moveu.current) onSelect?.(n);
                }}
                onDoubleClick={() => onExpand?.(n)}
              >
                <title>
                  {n.name} ({n.type}){grau ? ` — ${grau} relação(ões)` : ''}
                  {ehBase(n) ? ' — conhecimento base' : ''}
                  {n.expanded === false ? ' — duplo clique para expandir' : ''}
                </title>
                <circle
                  r={raio}
                  fill={corDe(n.type)}
                  fillOpacity={selecionado || ehCentro ? 1 : 0.75}
                  stroke={
                    selecionado
                      ? 'var(--vscode-focusBorder)'
                      : ehCentro
                        ? 'var(--vscode-textLink-foreground)'
                        : 'var(--vscode-panel-border)'
                  }
                  strokeWidth={selecionado || ehCentro ? 2 : 1}
                />
                {/* Anel tracejado = tem vizinho não carregado. É o convite à
                    expansão progressiva, em vez de carregar tudo (§12). */}
                {n.expanded === false && (
                  <circle
                    r={raio + 3}
                    fill="none"
                    stroke="var(--vscode-descriptionForeground)"
                    strokeDasharray="2 2"
                    strokeWidth={1}
                  />
                )}
                {/* Quadrado = veio de fonte base, fora deste repositório. */}
                {ehBase(n) && (
                  <rect
                    x={raio - 1}
                    y={-raio - 5}
                    width={5}
                    height={5}
                    fill="var(--vscode-charts-orange, #d18616)"
                  />
                )}
                {mostrarNome(n.id) && (
                  <text
                    y={-raio - 5}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--vscode-foreground)"
                    // O contorno separa o nome das linhas que passam atrás.
                    stroke="var(--vscode-editor-background)"
                    strokeWidth={2.5}
                    paintOrder="stroke"
                  >
                    {n.name.length > 24 ? n.name.slice(0, 23) + '…' : n.name}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="flex items-center gap-2 px-2 py-1 border-t border-border text-[0.8em] text-fg-muted flex-wrap">
        <span>
          Clique seleciona · duplo clique expande · arraste move · <kbd>+</kbd>{' '}
          <kbd>−</kbd> <kbd>0</kbd>
        </span>
        {foco && onOpen && (
          <button
            type="button"
            className="ml-auto text-link hover:underline"
            onClick={() => {
              const n = visivel.nodes.find((x) => x.id === foco);
              if (n) onOpen(n);
            }}
          >
            Abrir a fonte do nó em foco
          </button>
        )}
      </div>
    </div>
  );
}

/** Nó com mais relações desenha maior — o hub fica óbvio sem precisar contar. */
function raioDe(grau: number): number {
  return 4.5 + Math.min(5, Math.sqrt(grau) * 1.6);
}

/**
 * Layout dirigido por forças, determinístico.
 *
 * Posição inicial vem de um hash do id, não de `Math.random()`: sem isso o
 * mesmo grafo sai diferente a cada render e a pessoa perde a referência visual
 * que acabou de construir.
 *
 * As distâncias escalam com a raiz do número de nós. Com constante fixa, vinte
 * nós ficavam esparsos demais e cem viravam um novelo no meio da tela.
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
  const escala = Math.max(0.6, Math.min(1.8, Math.sqrt(24 / Math.max(4, nodes.length)) * 1.2));
  const distanciaAresta = 95 * escala;
  const repulsao = 950 * escala * escala;

  const pos: Pos[] = nodes.map((n, i) => {
    if (n.id === center) return { id: n.id, x: cx, y: cy, vx: 0, vy: 0 };
    const angulo = (hash(n.id) % 360) * (Math.PI / 180);
    const raio = (60 + (i % 5) * 28) * escala;
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
        const forca = repulsao / d2;
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
      const forca = (d - distanciaAresta) * 0.02;
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
      p.x = Math.max(28, Math.min(largura - 28, p.x));
      p.y = Math.max(22, Math.min(altura - 18, p.y));
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

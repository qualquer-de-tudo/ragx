import { useEffect, useId, useRef, useState } from 'react'
import type { SavingsDay, SavingsSeries } from '../../../electron/data/types'
import { formatNumber, formatPercent } from '../../format'
import { TrialEstimate } from '../EstimatePanel'

const HEIGHT = 200
const PAD = { top: 12, right: 8, bottom: 24, left: 44 }
/** Gap de superfície entre as duas barras de um dia (spec de marcas: 2px). */
const GAP = 2

function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}

function longDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' })
}

/** Número compacto para o eixo: 12 mil, 1,2 mi. */
function compact(n: number): string {
  return new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
}

/** Teto "redondo" do eixo e três linhas de grade. */
function niceMax(v: number): number {
  if (v <= 0) return 1
  const exp = 10 ** Math.floor(Math.log10(v))
  const f = v / exp
  const step = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10
  return step * exp
}

/** Barra com o topo arredondado (4px) e a base reta, presa na linha de base. */
function barPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0 || w <= 0) return ''
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

function saved(day: { baseline: number; delivered: number }): number {
  return day.baseline > 0 ? (day.baseline - day.delivered) / day.baseline : 0
}

function Chart({ days }: { days: SavingsDay[] }) {
  const [wrapRef, width] = useWidth<HTMLDivElement>(640)
  const [hover, setHover] = useState<number | null>(null)
  const plotW = width - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const max = niceMax(Math.max(...days.map((d) => Math.max(d.baseline, d.delivered))))
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH
  const slot = plotW / days.length
  const barW = Math.max(2, Math.min(18, (slot * 0.7 - GAP) / 2))
  const groupW = barW * 2 + GAP
  const ticks = [0, max / 2, max]
  // Rótulo de data a cada N dias para não encavalar.
  const every = slot < 34 ? Math.ceil(34 / slot) : 1
  const active = hover !== null ? days[hover] : null

  return (
    <div className="savings-chart" ref={wrapRef}>
      <svg width={width} height={HEIGHT} role="img" aria-label="Tokens por dia, sem e com o RAGX" onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="chart-grid" x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="chart-axis" x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
              {compact(t)}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const x0 = PAD.left + i * slot + (slot - groupW) / 2
          return (
            <g key={d.date}>
              {hover === i && <rect className="chart-hover" x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} />}
              <path className="bar-baseline" d={barPath(x0, y(d.baseline), barW, PAD.top + plotH - y(d.baseline))} />
              <path className="bar-delivered" d={barPath(x0 + barW + GAP, y(d.delivered), barW, PAD.top + plotH - y(d.delivered))} />
              {(i % every === 0 || i === days.length - 1) && (
                <text className="chart-axis" x={PAD.left + i * slot + slot / 2} y={HEIGHT - 6} textAnchor="middle">
                  {shortDate(d.date)}
                </text>
              )}
              {/* Alvo do hover: a coluna inteira do dia, maior que as barras. */}
              <rect
                className="chart-hit"
                x={PAD.left + i * slot}
                y={PAD.top}
                width={slot}
                height={plotH}
                onMouseEnter={() => setHover(i)}
              />
            </g>
          )
        })}
      </svg>
      {active && hover !== null && (
        <div
          className="chart-tooltip"
          role="status"
          style={{
            left: Math.min(Math.max(PAD.left + hover * slot + slot / 2, 90), width - 90),
          }}
        >
          <p className="chart-tooltip-title">{longDate(active.date)}</p>
          {active.calls === 0 ? (
            <p className="dim">sem consultas</p>
          ) : (
            <dl>
              <div>
                <dt>
                  <span className="swatch swatch-baseline" aria-hidden="true" /> Sem RAGX
                </dt>
                <dd>{formatNumber(active.baseline)}</dd>
              </div>
              <div>
                <dt>
                  <span className="swatch swatch-delivered" aria-hidden="true" /> Com RAGX
                </dt>
                <dd>{formatNumber(active.delivered)}</dd>
              </div>
              <div>
                <dt>Economia</dt>
                <dd>{formatPercent(saved(active))}</dd>
              </div>
            </dl>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Tokens que os agentes gastariam lendo os arquivos inteiros ("sem RAGX")
 * contra o que o `build_context` de fato entregou ("com RAGX"), por dia. Os
 * dois números vêm do log do servidor MCP, do uso real, a partir da versão
 * que passou a gravar o "sem RAGX". A simulação (`ragx trial`) fica embaixo,
 * para quando ainda não há uso.
 */
export function TokenSavings({
  projectId,
  projectPath,
  savings,
}: {
  projectId: string
  projectPath: string | null
  savings: SavingsSeries | undefined
}) {
  const titleId = useId()
  const has = savings !== undefined && savings.calls > 0
  const economy = has ? saved(savings) : 0

  return (
    <section className="card detail-card savings" aria-labelledby={titleId}>
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          Economia de tokens
        </h2>
        <span className="hint">últimos {savings?.days.length ?? 14} dias</span>
      </div>

      {has ? (
        <>
          <div className="savings-head">
            <p className="trial-figure">
              <span className="trial-value">{formatPercent(Math.abs(economy))}</span>
              <span className="trial-unit">{economy >= 0 ? 'menos tokens' : 'mais tokens'}</span>
            </p>
            <dl className="pairs savings-pairs">
              <div>
                <dt>
                  <span className="swatch swatch-baseline" aria-hidden="true" /> Sem RAGX
                </dt>
                <dd>{formatNumber(savings.baseline)}</dd>
              </div>
              <div>
                <dt>
                  <span className="swatch swatch-delivered" aria-hidden="true" /> Com RAGX
                </dt>
                <dd>{formatNumber(savings.delivered)}</dd>
              </div>
              <div>
                <dt>Economizados</dt>
                <dd>{formatNumber(savings.baseline - savings.delivered)}</dd>
              </div>
              <div>
                <dt>Consultas</dt>
                <dd>{formatNumber(savings.calls)}</dd>
              </div>
            </dl>
          </div>
          <Chart days={savings.days} />
          <details className="savings-table">
            <summary>Ver em tabela</summary>
            <table>
              <thead>
                <tr>
                  <th scope="col">Dia</th>
                  <th scope="col">Sem RAGX</th>
                  <th scope="col">Com RAGX</th>
                  <th scope="col">Economia</th>
                </tr>
              </thead>
              <tbody>
                {savings.days
                  .filter((d) => d.calls > 0)
                  .map((d) => (
                    <tr key={d.date}>
                      <th scope="row">{shortDate(d.date)}</th>
                      <td>{formatNumber(d.baseline)}</td>
                      <td>{formatNumber(d.delivered)}</td>
                      <td>{formatPercent(saved(d))}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
          <p className="hint">
            "Sem RAGX" é o tamanho dos arquivos inteiros de onde cada contexto saiu, estimado em ~4 caracteres por
            token. Conta só as chamadas de build_context.
          </p>
        </>
      ) : (
        <p className="dim">
          Ainda sem medições de uso real neste projeto. O gráfico enche sozinho quando um agente usar o build_context
          do RAGX aqui. Enquanto isso, dá para simular abaixo.
        </p>
      )}

      <TrialEstimate projectId={projectId} projectPath={projectPath} />
    </section>
  )
}

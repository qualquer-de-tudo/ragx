import { useId } from 'react'
import {
  benchmarks,
  changeOf,
  formatDate,
  formatPct,
  formatValue,
  goalsMet,
  groups,
  type BenchmarkData,
  type Metric,
} from '../../benchmarks'

/** As duas barras do antes e do depois, na mesma escala: a diferença se vê sem ler o número. */
function Bars({ metric }: { metric: Metric }) {
  const { before, after } = changeOf(metric)
  if (before === null) return null
  const max = Math.max(before, after) || 1
  return (
    <div className="bench-bars" aria-hidden="true">
      <div className="bench-bar bench-bar-before" style={{ width: `${(before / max) * 100}%` }} />
      <div className="bench-bar bench-bar-after" style={{ width: `${Math.max((after / max) * 100, 1.5)}%` }} />
    </div>
  )
}

function MetricCard({ metric }: { metric: Metric }) {
  const titleId = useId()
  const c = changeOf(metric)
  const tone = c.better === null ? 'none' : c.better ? 'good' : 'bad'
  const basePoint = metric.points[0]
  return (
    <article className="card bench-card" aria-labelledby={titleId}>
      <h4 className="bench-name" id={titleId}>
        {metric.name}
      </h4>
      <p className="bench-detail">{metric.detail}</p>
      <p className="bench-now">
        <span className="bench-value">{formatValue(c.after, metric.unit)}</span>
        {c.pct !== null && <span className={`bench-delta bench-delta-${tone}`}>{formatPct(c.pct)}</span>}
      </p>
      <Bars metric={metric} />
      <p className="bench-before">
        {c.before === null ? `Antes: ${basePoint.note ?? 'sem medição'}` : `Antes: ${formatValue(c.before, metric.unit)}`}
      </p>
      {metric.goal && (
        <p className={`bench-goal ${metric.goal.met ? 'bench-goal-met' : 'bench-goal-missed'}`}>
          Meta {metric.lowerIsBetter ? 'até' : 'de'} {formatValue(metric.goal.value, metric.unit)}:{' '}
          <strong>{metric.goal.met ? 'atingida' : 'não atingida'}</strong>
        </p>
      )}
      {metric.caveat && <p className="bench-caveat">{metric.caveat}</p>}
      <details className="bench-method">
        <summary>Como foi medido</summary>
        {basePoint.note && c.before !== null && <p>{basePoint.note}.</p>}
        <p className="mono">{metric.method}</p>
      </details>
    </article>
  )
}

function AbSection({ ab }: { ab: BenchmarkData['ab'] }) {
  const id = useId()
  return (
    <section className="card bench-ab" aria-labelledby={id}>
      <div className="bench-ab-head">
        <h3 className="card-title" id={id}>
          {ab.title}
        </h3>
        <p className="bench-verdict">{ab.verdict}</p>
      </div>
      <p className="bench-setup">{ab.setup}</p>
      <table className="bench-table">
        <thead>
          <tr>
            <th scope="col">Medida</th>
            <th scope="col">Sem RAGX</th>
            <th scope="col">Com RAGX</th>
            <th scope="col">Leitura</th>
          </tr>
        </thead>
        <tbody>
          {ab.rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td>{r.without}</td>
              <td>{r.with}</td>
              <td className="dim">{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="bench-reading">{ab.reading}</p>
      <details className="bench-method">
        <summary>Como foi medido</summary>
        <p className="mono">{ab.method}</p>
      </details>
    </section>
  )
}

/** 0,6 vira "0,60": o recall sempre com duas casas. */
function r2(n: number): string {
  return n.toFixed(2).replace('.', ',')
}

function ci(range: [number, number]): string {
  return `${r2(range[0])} a ${r2(range[1])}`
}

function RetrievalSection({ r }: { r: BenchmarkData['retrieval'] }) {
  const id = useId()
  return (
    <section className="card bench-retrieval" aria-labelledby={id}>
      <h3 className="card-title" id={id}>
        {r.title}
      </h3>
      <p className="bench-setup">{r.intro}</p>
      <table className="bench-table">
        <thead>
          <tr>
            <th scope="col">Modelo de embedding</th>
            <th scope="col">132 consultas à mão</th>
            <th scope="col">134 do histórico do git</th>
            <th scope="col">Latência da consulta</th>
          </tr>
        </thead>
        <tbody>
          {r.rows.map((row) => (
            <tr key={row.model}>
              <th scope="row">{row.model}</th>
              <td>
                <strong>{r2(row.manual)}</strong> <span className="dim">({ci(row.manualCi)})</span>
              </td>
              <td>
                <strong>{r2(row.git)}</strong> <span className="dim">({ci(row.gitCi)})</span>
              </td>
              <td>{row.queryMs.toLocaleString('pt-BR')} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="bench-reading">{r.note}</p>
      <details className="bench-method">
        <summary>Como foi medido</summary>
        <p className="mono">{r.method}</p>
      </details>
    </section>
  )
}

function Timeline({ data }: { data: BenchmarkData }) {
  const byId = new Map(data.metrics.map((m) => [m.id, m]))
  return (
    <ol className="bench-timeline">
      {[...data.timeline].reverse().map((e) => (
        <li key={`${e.date}-${e.title}`} className="bench-event">
          <span className="bench-event-dot" aria-hidden="true" />
          <p className="bench-event-when">
            {formatDate(e.date)} <span className="dim">· versão {e.version}</span>
          </p>
          <h4 className="bench-event-title">{e.title}</h4>
          <p className="bench-event-text">{e.text}</p>
          {e.metrics.length > 0 && (
            <ul className="bench-chips" aria-label="Números desta etapa">
              {e.metrics.flatMap((id) => {
                const m = byId.get(id)
                if (!m) return []
                const c = changeOf(m)
                return [
                  <li key={id} className="bench-chip">
                    {m.name}: {c.before === null ? 'sem base' : formatValue(c.before, m.unit)} → <strong>{formatValue(c.after, m.unit)}</strong>
                  </li>,
                ]
              })}
            </ul>
          )}
        </li>
      ))}
    </ol>
  )
}

/**
 * Aba "Benchmarks" do Como funciona: o que o RAGX mediu de si mesmo, com antes e depois, método e data; a medição
 * contra um agente sem RAGX, com o resultado como ele foi; e a linha do tempo das etapas. Tudo vem de
 * `data/benchmarks.json` (embutido: nenhuma chamada de rede).
 */
export function BenchmarksView({ data = benchmarks }: { data?: BenchmarkData }) {
  const { met, total } = goalsMet(data.metrics)
  return (
    <div className="bench">
      <header className="bench-head">
        <p className="bench-lede">{data.intro}</p>
        <p className="bench-meta">
          <span className="bench-pill">
            {met} de {total} metas atingidas
          </span>
          <span className="dim">
            Atualizado em {formatDate(data.updated)} · {data.environment}
          </span>
        </p>
      </header>

      {groups(data.metrics).map((g) => (
        <section key={g.name} className="bench-group" aria-label={g.name}>
          <h3 className="bench-group-title">{g.name}</h3>
          <div className="bench-grid">
            {g.metrics.map((m) => (
              <MetricCard key={m.id} metric={m} />
            ))}
          </div>
        </section>
      ))}

      <AbSection ab={data.ab} />
      <RetrievalSection r={data.retrieval} />

      <section className="card bench-time" aria-labelledby="bench-time-title">
        <h3 className="card-title" id="bench-time-title">
          Linha do tempo
        </h3>
        <Timeline data={data} />
      </section>
    </div>
  )
}

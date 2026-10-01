import { useId } from 'react'
import type { JobView, ProjectSnapshot } from '../../types/ragx-bridge'
import type { ProjectStatus } from '../../projectStatus'
import { computeIndexHealth, runDuration, type HealthLevel } from '../../indexHealth'
import { busyProjectIds, deriveProjectState } from '../../state'
import { formatNumber, formatTime } from '../../format'
import { Badge } from '../shell/Badge'
import { JobButton } from './JobButton'

const LEVEL_LABEL: Record<HealthLevel, string> = { ok: 'Saudável', warn: 'Atenção', bad: 'Com problema' }
const LEVEL_TONE = { ok: 'good', warn: 'warning', bad: 'critical' } as const

function seconds(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`
}

const BAR_MAX_H = 56
const BAR_W = 14
const BAR_GAP = 6

/** Barras com a duração das últimas indexações, da mais antiga (esquerda) à mais nova (direita). */
function DurationChart({ items }: { items: Array<{ label: string; ms: number; failed: boolean }> }) {
  const max = Math.max(...items.map((i) => i.ms), 1)
  const width = items.length * (BAR_W + BAR_GAP)
  return (
    <svg className="health-chart" width={width} height={BAR_MAX_H + 4} role="group" aria-label="Duração das últimas indexações">
      {items.map((it, i) => {
        const h = Math.max(2, Math.round((it.ms / max) * BAR_MAX_H))
        return (
          <rect
            key={i}
            className={`health-bar${it.failed ? ' is-failure' : ''}`}
            x={i * (BAR_W + BAR_GAP)}
            y={BAR_MAX_H + 4 - h}
            width={BAR_W}
            height={h}
            rx={2}
            role="img"
            aria-label={`${it.label}: ${seconds(it.ms)}${it.failed ? ', falhou' : ''}`}
          />
        )
      })}
    </svg>
  )
}

/**
 * "Saúde do índice" (RAGX-0189): selo de nível em texto, as checagens e a tendência das últimas indexações. A defasagem
 * em si fica em "Está em dia?". Dado ausente diz "sem dado", nunca "ok". A tendência é a das INDEXAÇÕES (as 10 mais
 * recentes de `ragx status`), não uma série de cobertura.
 */
export function IndexHealth({
  project,
  status,
  jobs,
}: {
  project: ProjectSnapshot
  status: ProjectStatus | null
  jobs: readonly JobView[]
}) {
  const titleId = useId()
  const state = deriveProjectState(project, busyProjectIds(jobs))
  const health = computeIndexHealth({ project, state, status })
  const runs = status?.runs ?? []
  const withDuration = [...runs].reverse().flatMap((r) => {
    const ms = runDuration(r)
    return ms === null ? [] : [{ label: r.finishedAt ? formatTime(r.finishedAt) : 'sem hora', ms, failed: r.error !== null }]
  })

  return (
    <section className="card detail-card" aria-labelledby={titleId}>
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          Saúde do índice
        </h2>
        <Badge tone={LEVEL_TONE[health.level]}>{LEVEL_LABEL[health.level]}</Badge>
      </div>

      <ul className="health-checks" aria-label="Checagens">
        {health.checks.map((c) => (
          <li key={c.id} className="health-check">
            <span className={`health-level health-level-${c.level}`}>{LEVEL_LABEL[c.level]}</span> {c.text}{' '}
            {c.action !== null && (
              <JobButton
                kind={c.action}
                label={c.action === 'embed' ? 'Gerar embeddings' : 'Instalar hooks'}
                projectId={project.id}
                jobs={jobs}
                disabled={!project.exists}
              />
            )}
          </li>
        ))}
      </ul>

      <p className="health-trend">
        <strong>Tendência das indexações:</strong> {health.trend.text}
        {health.trend.failures > 0 && ` · ${formatNumber(health.trend.failures)} falha(s) nas últimas ${formatNumber(health.trend.runs)}`}
      </p>
      {(health.trend.medianNoChangeMs !== null || health.trend.medianWithChangeMs !== null) && (
        <p className="hint">
          Mediana sem mudança: {health.trend.medianNoChangeMs === null ? 'sem dado' : seconds(health.trend.medianNoChangeMs)} · com
          mudança: {health.trend.medianWithChangeMs === null ? 'sem dado' : seconds(health.trend.medianWithChangeMs)}.
        </p>
      )}

      {withDuration.length > 0 && (
        <>
          <DurationChart items={withDuration} />
          <details className="savings-table">
            <summary>Ver em tabela</summary>
            <table>
              <thead>
                <tr>
                  <th scope="col">Quando</th>
                  <th scope="col">Duração</th>
                  <th scope="col">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {withDuration.map((it, i) => (
                  <tr key={i}>
                    <th scope="row">{it.label}</th>
                    <td>{seconds(it.ms)}</td>
                    <td>{it.failed ? 'falhou' : 'ok'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  )
}

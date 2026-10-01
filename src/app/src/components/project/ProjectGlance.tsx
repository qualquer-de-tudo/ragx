import type { ReactNode } from 'react'
import type { JobView, ProjectSnapshot } from '../../types/ragx-bridge'
import { STATE_ACTION, type ProjectState } from '../../state'
import { formatCompact, formatNumber, formatPercent } from '../../format'
import { reasonText, type StatusView } from '../../projectStatus'
import { savingsRatio, tokensSaved } from '../../projectMetrics'
import { JobButton } from './JobButton'
import { RelativeTime } from '../shell/RelativeTime'
import { SkeletonRegion, SkeletonText } from '../ui/Skeleton'

/** Um bloco da faixa. Cada bloco é uma entrada de lista para outras tarefas (moeda, saúde do índice) acrescentarem. */
interface GlanceBlock {
  id: string
  title: string
  body: ReactNode
}

/** A resposta de "o índice está em dia?" em uma linha de texto (o estado nunca fica só na cor). */
function freshnessLine(status: StatusView): ReactNode {
  if (status.phase === 'loading') {
    return (
      <SkeletonRegion label="Verificando…">
        <SkeletonText lines={1} />
      </SkeletonRegion>
    )
  }
  if (status.phase === 'error') return 'Sem resposta do ragx status; o motivo está em Visão geral.'
  const { state: freshness, reasons } = status.status.freshness
  if (freshness === 'fresh') return `Índice em dia.`
  if (freshness === 'stale') return `Índice defasado: ${reasons.length > 0 ? reasonText(reasons[0]) : 'precisa ser atualizado.'}`
  return 'Estado do índice desconhecido; veja o motivo em Visão geral.'
}

/** Os blocos, na ordem da faixa. Puro: quem renderiza decide o layout. */
interface GlanceProps {
  project: ProjectSnapshot
  state: ProjectState
  status: StatusView
  live: boolean
  jobs: readonly JobView[]
  onSeeSavings: () => void
}

function glanceBlocks(args: GlanceProps): GlanceBlock[] {
  const { project, state, status, live, jobs, onSeeSavings } = args
  const action = STATE_ACTION[state]
  const ratio = savingsRatio(project)
  const last = project.telemetry.lastCallAt

  return [
    {
      id: 'freshness',
      title: 'Está em dia?',
      body: (
        <>
          <div className="glance-main">{freshnessLine(status)}</div>
          {action !== null && action.kind !== 'open' && (
            <JobButton
              kind={action.kind}
              label={action.kind === 'update' ? 'Atualizar' : action.label}
              projectId={project.id}
              jobs={jobs}
              primary
              disabled={!project.exists}
            />
          )}
        </>
      ),
    },
    {
      id: 'savings',
      title: 'Economia (14 dias)',
      body: (
        <>
          <div className="glance-main">
            {ratio === null
              ? 'Sem medição ainda.'
              : `${formatPercent(ratio)} menos tokens, ${formatCompact(tokensSaved(project))} economizados.`}
          </div>
          <button type="button" className="btn btn-quiet btn-sm" onClick={onSeeSavings}>
            Ver gráfico
          </button>
        </>
      ),
    },
    {
      id: 'agent',
      title: 'Agente usando?',
      body: (
        <div className="glance-main">
          {live ? (
            'Em uso agora: o agente chamou o RAGX no último minuto.'
          ) : last ? (
            <>
              Última chamada <RelativeTime iso={last} />, {formatNumber(project.telemetry.totalCalls)} chamada(s) em 24 h.
            </>
          ) : (
            'Nenhuma chamada registrada. Confira em Conexões se o RAGX está ligado no Claude Code.'
          )}
        </div>
      ),
    },
  ]
}

/**
 * Faixa "de relance" no topo do detalhe, visível em todas as abas (RAGX-0184): as três perguntas de quem abre o
 * projeto, antes das abas. Os dados vêm do snapshot e de `ragx status --json`, que a página já pede.
 */
export function ProjectGlance(props: GlanceProps) {
  return (
    <section className="glance" aria-label="De relance">
      {glanceBlocks(props).map((b) => (
        <div key={b.id} className="card glance-block" role="group" aria-label={b.title}>
          <h2 className="glance-title">{b.title}</h2>
          {b.body}
        </div>
      ))}
    </section>
  )
}

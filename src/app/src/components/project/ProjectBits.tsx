import type { JobKind, JobView, ProjectSnapshot } from '../../types/ragx-bridge'
import { STATE_ACTION, jobStateLabel, type ProjectState } from '../../state'
import { formatCompact, formatNumber, formatPercent } from '../../format'
import { savingsRatio } from '../../projectMetrics'

/**
 * O botão que faz o que o estado pede (`STATE_ACTION`), igual no card e na
 * lista. Sem ação de fila (pasta ausente, erro, atualizado), abre o detalhe;
 * com tarefa do mesmo tipo na fila ou rodando, diz isso e espera.
 */
export function ProjectActionButton({
  project,
  state,
  active,
  onOpen,
  onAction,
  block = false,
}: {
  project: ProjectSnapshot
  state: ProjectState
  active: JobView | null
  onOpen: () => void
  onAction: (kind: JobKind) => void
  block?: boolean
}) {
  const extra = block ? ' btn-block' : ' btn-sm'
  const action = STATE_ACTION[state]
  if (state === 'indexing') {
    return (
      <button type="button" className={`btn${extra}`} disabled>
        Indexando…
      </button>
    )
  }
  if (action === null || action.kind === 'open') {
    return (
      <button type="button" className={`btn${extra}`} onClick={onOpen} aria-label={block ? undefined : `${action?.label ?? 'Ver detalhes'}: ${project.name}`}>
        {action?.label ?? 'Ver detalhes'}
      </button>
    )
  }
  const kind = action.kind
  const busy = active ? jobStateLabel(active) : null
  return (
    <button
      type="button"
      className={`btn btn-primary${extra}`}
      disabled={busy !== null}
      aria-label={busy ? `${action.label}: ${busy.toLowerCase()}` : block ? undefined : `${action.label}: ${project.name}`}
      onClick={() => onAction(kind)}
    >
      {busy ?? action.label}
    </button>
  )
}

/** Economia, chamadas nas últimas 24 h e documentos, lado a lado no card. */
export function ProjectNumbers({ project }: { project: ProjectSnapshot }) {
  const ratio = savingsRatio(project)
  const docs = project.counts?.documents ?? null
  return (
    <dl className="project-numbers">
      <div>
        <dt>Economia</dt>
        <dd title="Menos tokens que ler os arquivos inteiros, nos últimos 14 dias">{ratio === null ? 'sem uso' : formatPercent(ratio)}</dd>
      </div>
      <div>
        <dt>Chamadas 24 h</dt>
        <dd>{formatNumber(project.telemetry.totalCalls)}</dd>
      </div>
      <div>
        <dt>Documentos</dt>
        <dd>{docs === null ? 'sem dados' : formatCompact(docs)}</dd>
      </div>
    </dl>
  )
}

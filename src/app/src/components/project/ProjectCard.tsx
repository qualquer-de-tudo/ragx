import { useId, type MouseEvent } from 'react'
import type { JobKind, JobView, ProjectSnapshot } from '../../types/ragx-bridge'
import { STATE_ACTION, STATE_LABEL, STATE_TONE, type ProjectState } from '../../state'
import { formatCompact, formatEta, formatRelative } from '../../format'
import { Badge } from '../shell/Badge'

function BranchIcon() {
  return (
    <svg
      className="project-card-icon"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="6" cy="5" r="2.2" />
      <circle cx="6" cy="19" r="2.2" />
      <circle cx="18" cy="7" r="2.2" />
      <path d="M6 7.2v9.6" />
      <path d="M18 9.2c0 5-6 4-11 7.8" />
    </svg>
  )
}

function branchLine(project: ProjectSnapshot): { current: string; indexBranch: string | null } {
  const git = project.git
  if (!git) return { current: 'Sem git', indexBranch: null }
  const current = git.branch ?? `HEAD destacado em ${git.commit.slice(0, 7)}`
  const indexBranch = project.index?.branch ?? null
  // Aviso só quando os dois lados têm branch e elas diferem (HEAD destacado
  // no mesmo commit não é "outra branch").
  const differs = git.branch !== null && indexBranch !== null && indexBranch !== git.branch
  return { current, indexBranch: differs ? indexBranch : null }
}

/**
 * Card de um projeto na grade. O botão principal faz a ação do estado
 * (`STATE_ACTION`); clicar em qualquer outro lugar do card abre o detalhe.
 * Para o teclado, o nome do projeto é um botão que também abre o detalhe.
 */
export function ProjectCard({
  project,
  state,
  hint,
  job = null,
  onOpen,
  onAction,
}: {
  project: ProjectSnapshot
  state: ProjectState
  /** Onde o projeto mora (`parentHint`); `null` quando não há caminho. */
  hint: string | null
  /** Tarefa desta fila para o projeto, se houver: dá a barra de progresso. */
  job?: JobView | null
  onOpen: (id: string) => void
  onAction: (kind: JobKind) => void
}) {
  const titleId = useId()
  const open = () => onOpen(project.id)

  const onCardClick = (e: MouseEvent<HTMLElement>) => {
    // Clique que nasceu num botão (inclusive desabilitado) é do botão.
    if ((e.target as Element).closest('button')) return
    // Selecionar texto (ex.: copiar o nome da branch) não abre o detalhe.
    if (window.getSelection()?.toString()) return
    open()
  }

  const { current, indexBranch } = branchLine(project)
  const counts = project.counts
  const missingEmbeddings = counts !== null && (counts.pendingEmbeddings > 0 || counts.embeddings < counts.chunks)
  const coverage = counts && counts.chunks > 0 ? Math.min(1, counts.embeddings / counts.chunks) : 0
  const embLegend = counts
    ? `${formatCompact(counts.embeddings)} de ${formatCompact(counts.chunks)} chunks com embedding`
    : 'Embeddings: sem dados'

  const running = job && job.state === 'running' && job.total !== null && job.total > 0 ? job : null
  const progressDone = running ? Math.min(running.done ?? 0, running.total ?? 0) : 0

  const action = STATE_ACTION[state]

  let button
  if (state === 'indexing') {
    button = (
      <button type="button" className="btn btn-block" disabled>
        Indexando…
      </button>
    )
  } else if (action === null || action.kind === 'open') {
    // Sem ação de fila (pasta ausente, erro, atualizado): o botão abre o detalhe.
    button = (
      <button type="button" className="btn btn-block" onClick={open}>
        {action?.label ?? 'Ver detalhes'}
      </button>
    )
  } else {
    const kind = action.kind
    button = (
      <button type="button" className="btn btn-primary btn-block" onClick={() => onAction(kind)}>
        {action.label}
      </button>
    )
  }

  return (
    <article className="card project-card" aria-labelledby={titleId} onClick={onCardClick}>
      <div className="project-card-head">
        <h2 className="card-title project-card-title" id={titleId}>
          <button type="button" className="project-card-name" onClick={open}>
            {project.name}
          </button>
        </h2>
        <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
      </div>

      <p className="project-card-where">{hint ?? 'sem dados'}</p>

      <p className="project-card-line">
        <BranchIcon />
        <span className="project-card-branch">{current}</span>
        {indexBranch !== null && <span className="is-warning">índice da branch {indexBranch}</span>}
      </p>

      <p className="project-card-line">
        {project.index ? `Indexado ${formatRelative(project.index.finishedAt)}` : 'Ainda não indexado com esta versão'}
      </p>

      <div className="project-card-emb">
        <div
          className={`meter${missingEmbeddings ? ' is-warning' : ''}`}
          role="meter"
          aria-label="Cobertura de embeddings"
          aria-valuemin={0}
          aria-valuemax={counts?.chunks ?? 0}
          aria-valuenow={counts?.embeddings ?? 0}
          aria-valuetext={embLegend}
        >
          <div className="meter-fill" style={{ width: `${coverage * 100}%` }} />
        </div>
        <p className={`project-card-legend${missingEmbeddings ? ' is-warning' : ''}`}>{embLegend}</p>
      </div>

      <div className="project-card-foot">
        {running && (
          <div className="project-card-progress">
            <div
              className="progress"
              role="progressbar"
              aria-label="Progresso da indexação"
              aria-valuemin={0}
              aria-valuemax={running.total ?? 0}
              aria-valuenow={progressDone}
            >
              <div className="progress-fill" style={{ width: `${(progressDone / (running.total ?? 1)) * 100}%` }} />
            </div>
            {running.etaSeconds !== null && <p className="project-card-legend">Faltam {formatEta(running.etaSeconds)}</p>}
          </div>
        )}
        {button}
      </div>
    </article>
  )
}

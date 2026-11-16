import { memo, useId, type MouseEvent } from 'react'
import type { JobKind, JobView, ProjectSnapshot } from '../../types/ragx-bridge'
import { STATE_LABEL, STATE_TONE, type ProjectState } from '../../state'
import { formatCompact, formatEta } from '../../format'
import { ProjectActionButton, ProjectNumbers } from './ProjectBits'
import { Badge } from '../shell/Badge'
import { LivePill } from '../shell/LivePill'
import { RelativeTime } from '../shell/RelativeTime'
import { Icon } from '../ui/Icon'
import { NodeGlyph, type NodeState } from '../ui/NodeGlyph'

type Stop = { label: string; state: NodeState; text: string }

/**
 * O caminho do dado (ADR-0017): gate → índice → vetores → agente, cada parada com o estado que o card já conhece.
 * Sem índice ou sem números (`status.json`) não há o que mostrar: `null`, e o card omite a linha em vez de inventar.
 * O gate não tem número próprio no snapshot; ele passa a "ok" porque não existe índice sem passar por ele (o Security
 * Gate roda antes do parser, docs/02-seguranca.md).
 */
function dataPath(project: ProjectSnapshot, state: ProjectState): Stop[] | null {
  const counts = project.counts
  if (!project.exists || project.index === null || counts === null) return null
  const index: Stop =
    state === 'indexing'
      ? { label: 'índice', state: 'accent', text: 'indexando' }
      : state === 'error'
        ? { label: 'índice', state: 'critical', text: 'última tarefa falhou' }
        : state === 'stale'
          ? { label: 'índice', state: 'warning', text: 'defasado' }
          : { label: 'índice', state: 'good', text: 'em dia' }
  const missing = counts.pendingEmbeddings > 0 || counts.embeddings < counts.chunks
  const vectors: Stop =
    counts.chunks === 0
      ? { label: 'vetores', state: 'muted', text: 'sem chunks' }
      : missing
        ? { label: 'vetores', state: 'warning', text: 'embeddings faltando' }
        : { label: 'vetores', state: 'good', text: 'completos' }
  const calls = project.telemetry.totalCalls
  const agent: Stop =
    calls > 0
      ? { label: 'agente', state: 'good', text: `${calls} ${calls === 1 ? 'chamada' : 'chamadas'}` }
      : { label: 'agente', state: 'muted', text: 'sem uso' }
  return [{ label: 'gate', state: 'good', text: 'passou' }, index, vectors, agent]
}

function DataPath({ stops }: { stops: Stop[] }) {
  return (
    <ol className="data-path" aria-label="Caminho do dado">
      {stops.map((s, i) => (
        <li key={s.label} className="data-path-stop" data-next={stops[i + 1]?.state}>
          <NodeGlyph state={s.state} />
          <span className={`data-path-label data-path-${s.state}`}>{s.label}</span>
          <span className="sr-only">: {s.text}</span>
        </li>
      ))}
    </ol>
  )
}

/** A porta do cartão toma o tom do estado quando ele pede atenção. */
const CARD_TONE: Record<NodeState, string> = { good: '', accent: '', muted: '', warning: ' card-warning', critical: ' card-critical' }

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
export const ProjectCard = memo(function ProjectCard({
  project,
  state,
  hint,
  job = null,
  active = null,
  failure = null,
  attention = null,
  live = false,
  onOpen,
  onAction,
}: {
  project: ProjectSnapshot
  state: ProjectState
  /** Onde o projeto mora (`parentHint`); `null` quando não há caminho. */
  hint: string | null
  /** Tarefa desta fila para o projeto, se houver: dá a barra de progresso. */
  job?: JobView | null
  /** Tarefa na fila ou rodando do mesmo tipo da ação do botão: desabilita o botão. */
  active?: JobView | null
  /** Erro da última tarefa do projeto, quando ela falhou. */
  failure?: string | null
  /** Problema de embedding que o selo não mostra (`embeddingAttention`), em texto. */
  attention?: string | null
  /** Houve uso do RAGX (MCP ou comando de consulta) no último minuto. */
  live?: boolean
  onOpen: (id: string) => void
  /** Estável entre renders (o card é `memo`): recebe o projeto, em vez de uma closure por linha. */
  onAction: (project: ProjectSnapshot, kind: JobKind) => void
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

  const path = dataPath(project, state)
  const running = job && job.state === 'running' && job.total !== null && job.total > 0 ? job : null
  const progressDone = running ? Math.min(running.done ?? 0, running.total ?? 0) : 0

  const button = (
    <ProjectActionButton
      project={project}
      state={state}
      active={active}
      onOpen={open}
      onAction={(kind) => onAction(project, kind)}
      block
    />
  )

  return (
    <article className={`card project-card${CARD_TONE[STATE_TONE[state]]}`} aria-labelledby={titleId} onClick={onCardClick}>
      <div className="project-card-head">
        <h2 className="card-title project-card-title" id={titleId}>
          <button type="button" className="project-card-name" onClick={open}>
            {project.name}
          </button>
        </h2>
        <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
      </div>
      {live && <LivePill />}

      <p className="project-card-where">{hint ?? 'sem dados'}</p>

      <p className="project-card-line">
        <Icon name="branch" size={14} className="project-card-icon" />
        <span className="project-card-branch">{current}</span>
        {indexBranch !== null && <span className="is-warning">índice da branch {indexBranch}</span>}
      </p>

      <p className="project-card-line">
        {project.index ? (
          <>
            Indexado <RelativeTime iso={project.index.finishedAt} />
          </>
        ) : (
          'Ainda não indexado com esta versão'
        )}
      </p>

      {path !== null && <DataPath stops={path} />}

      <ProjectNumbers project={project} />

      <div className="project-card-emb">
        <div
          className={`meter${missingEmbeddings ? ' is-warning' : ''}${counts !== null && counts.chunks > 0 && coverage >= 1 ? ' is-complete' : ''}`}
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
        {attention !== null && <p className="project-card-legend is-warning">{attention}</p>}
      </div>

      <div className="project-card-foot">
        {running && (
          <div className="project-card-progress">
            <div
              className={`progress${progressDone >= (running.total ?? 0) ? ' is-complete' : ''}`}
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
        {failure !== null && <p className="project-card-failure">Última tarefa falhou: {failure}</p>}
        {button}
      </div>
    </article>
  )
})

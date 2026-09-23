import type { ProjectSnapshot } from '../types/ragx-bridge'
import type { ProjectStats, TelemetrySummary } from '../../electron/data/types'
import { formatNumber, formatPercent } from '../format'
import { deriveProjectState, STATE_LABEL } from '../state'
import { EstimatePanel } from './EstimatePanel'
import { SecurityPanel } from './SecurityPanel'

interface Props {
  project: ProjectSnapshot | null
}

// Sem fila de tarefas nesta tarefa (Task 5) - ver o mesmo comentário em
// ProjectList.tsx.
const NO_BUSY_IDS = new Set<string>()

export function ProjectDetail({ project }: Props) {
  if (!project) {
    return (
      <main className="detail detail-empty">
        <p>Selecione um projeto na lista.</p>
      </main>
    )
  }

  const state = deriveProjectState(project, NO_BUSY_IDS)
  const ok = state === 'ok'

  return (
    <main className="detail">
      <header className="detail-head">
        <h1>{project.name}</h1>
        {project.path && <p className="detail-path">{project.path}</p>}
        <dl className="meta">
          <div>
            <dt>Status</dt>
            <dd className={`status-line tone-${ok ? 'good' : 'serious'}`}>
              <span aria-hidden="true">{ok ? '✓' : '!'}</span> {STATE_LABEL[state]}
            </dd>
          </div>
          <div>
            <dt>Visibilidade</dt>
            <dd>{project.visibility}</dd>
          </div>
          {project.embeddingModel && (
            <div className="meta-model">
              <dt>Modelo de embedding</dt>
              <dd title={project.embeddingModel}>{project.embeddingModel}</dd>
            </div>
          )}
        </dl>
      </header>

      <section className="block" aria-labelledby="index-title">
        <h2 id="index-title">Índice</h2>
        {project.counts === null ? (
          <p className="callout">{project.countsUnavailableReason ?? 'sem dados'}</p>
        ) : (
          <IndexFigures stats={project.counts} />
        )}
      </section>

      <section className="block" aria-labelledby="usage-title">
        <h2 id="usage-title">Uso pelos agentes nas últimas 24h</h2>
        <UsageFigures telemetry={project.telemetry} />
      </section>

      <div className="panels">
        <EstimatePanel projectId={project.id} projectPath={project.path} />
        <SecurityPanel projectId={project.id} projectPath={project.path} />
      </div>
    </main>
  )
}

function IndexFigures({ stats }: { stats: ProjectStats }) {
  const coverage = stats.chunks > 0 ? Math.min(1, stats.embeddings / stats.chunks) : null
  const missing = stats.chunks - Math.min(stats.embeddings, stats.chunks)
  return (
    <>
    <div className="kpis">
      <div className="kpi">
        <p className="kpi-label">Documentos</p>
        <p className="kpi-value">{formatNumber(stats.documents)}</p>
      </div>
      <div className="kpi">
        <p className="kpi-label">Chunks</p>
        <p className="kpi-value">{formatNumber(stats.chunks)}</p>
      </div>
      <div className="kpi kpi-wide">
        <p className="kpi-label">Embeddings</p>
        <p className="kpi-value">{formatNumber(stats.embeddings)}</p>
        {coverage !== null && (
          <div className="meter-row">
            <div
              className={coverage < 1 ? 'meter meter-short' : 'meter'}
              role="meter"
              aria-label="Chunks com embedding"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(coverage * 100)}
            >
              <span style={{ width: `${coverage * 100}%` }} />
            </div>
            <span className="meter-caption">{formatPercent(coverage)} dos chunks com embedding</span>
          </div>
        )}
      </div>
    </div>
    {missing > 0 && (
      <p className="callout callout-warning">
        <span className="tone-warning" aria-hidden="true">▲ </span>
        {stats.embeddings === 0
          ? 'Nenhum chunk tem embedding: a busca semântica e a híbrida caem para só palavra-chave neste projeto.'
          : `${formatNumber(missing)} chunks sem embedding ficam de fora da busca semântica.`}{' '}
        Com o provedor de embedding rodando, gere os que faltam com <code>ragx index --embed-only</code>{' '}
        na pasta do projeto.
      </p>
    )}
    </>
  )
}

function UsageFigures({ telemetry }: { telemetry: TelemetrySummary }) {
  if (telemetry.totalCalls === 0) {
    return (
      <p className="empty-state">
        Nenhuma chamada nas últimas 24h. Elas aparecem aqui assim que um agente usar o servidor MCP do
        ragx neste projeto.
      </p>
    )
  }

  const tools = [...telemetry.callsByTool].sort((a, b) => b.count - a.count)
  const top = tools[0]?.count ?? 1

  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <p className="kpi-label">Chamadas MCP</p>
          <p className="kpi-value">{formatNumber(telemetry.totalCalls)}</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Tokens entregues</p>
          <p className="kpi-value">{formatNumber(telemetry.tokensDelivered)}</p>
          <p className="kpi-note">Medido nas respostas do build_context</p>
        </div>
      </div>
      <ul className="bars" aria-label="Chamadas por ferramenta">
        {tools.map((t) => (
          <li
            key={t.tool}
            title={`${t.tool}: ${formatNumber(t.count)} chamadas (${formatPercent(t.count / telemetry.totalCalls)})`}
          >
            <span className="bar-label">{t.tool}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${Math.max(1.5, (t.count / top) * 100)}%` }} />
            </span>
            <span className="bar-value">{formatNumber(t.count)}</span>
          </li>
        ))}
      </ul>
    </>
  )
}

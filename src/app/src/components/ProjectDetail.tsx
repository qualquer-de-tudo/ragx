import type { ProjectSnapshot } from '../types/ragx-bridge'

interface Props {
  project: ProjectSnapshot | null
}

export function ProjectDetail({ project }: Props) {
  if (!project) {
    return <main className="project-detail"><p>Selecione um projeto à esquerda.</p></main>
  }

  const { stats, telemetry } = project

  return (
    <main className="project-detail">
      <h1>{project.name}</h1>
      <p className="path">{project.path}</p>

      <section>
        <h2>Índice</h2>
        {'unavailable' in stats ? (
          <p className="warning">{stats.reason}</p>
        ) : (
          <dl className="stat-grid">
            <div><dt>Documentos</dt><dd>{stats.documents}</dd></div>
            <div><dt>Chunks</dt><dd>{stats.chunks}</dd></div>
            <div><dt>Embeddings</dt><dd>{stats.embeddings}</dd></div>
          </dl>
        )}
      </section>

      <section>
        <h2>Chamadas MCP (últimas 24h)</h2>
        {telemetry.totalCalls === 0 ? (
          <p className="empty-hint">Nenhuma chamada registrada ainda.</p>
        ) : (
          <>
            <p>
              <strong>{telemetry.totalCalls}</strong> chamadas · <strong>{telemetry.tokensDelivered}</strong> tokens entregues (real)
            </p>
            <ul className="call-breakdown">
              {telemetry.callsByTool.map((c) => (
                <li key={c.tool}>{c.tool}: {c.count}</li>
              ))}
            </ul>
          </>
        )}
        <p className="estimate-note">
          Economia estimada não é calculada automaticamente — é um proxy (ver <code>ragx trial</code>), não um número ao vivo.
        </p>
      </section>
    </main>
  )
}

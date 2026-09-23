import type { ConnectionCheck, JobView } from '../types/ragx-bridge'
import { ConnectionGrid } from '../components/connections/ConnectionCard'

/**
 * Tela Conexões: RAGX CLI, Claude Code e Ollama (Docker), cada um com selo,
 * fatos e as correções de um clique. A checagem mora no `App`
 * (`useConnections`), que também alimenta o ponto de saúde do topo.
 */
export function ConnectionsPage({
  connections,
  checking,
  onRefresh,
  jobs,
}: {
  connections: ConnectionCheck[] | null
  checking: boolean
  onRefresh: () => void
  jobs: readonly JobView[]
}) {
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Conexões</h1>
          <p className="page-lede">O painel confere estas três peças a cada 30 segundos.</p>
        </div>
        <button type="button" className="btn" onClick={onRefresh} disabled={checking}>
          {checking ? 'Verificando…' : 'Verificar agora'}
        </button>
      </header>
      <ConnectionGrid connections={connections} jobs={jobs} />
    </section>
  )
}

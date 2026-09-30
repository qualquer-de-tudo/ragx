import type { ConnectionCheck, JobView } from '../types/ragx-bridge'
import { ConnectionGrid } from '../components/connections/ConnectionCard'
import { ClaudeProfiles } from '../components/connections/ClaudeProfiles'
import type { ClaudeToggle } from '../hooks/useClaudeIntegration'

/**
 * Tela Conexões: RAGX CLI, Claude Code e Ollama (no Docker ou local), cada um
 * com selo, fatos e as correções de um clique; no Ollama também trocar de
 * modo, parar e medir a velocidade. A checagem mora no `App`
 * (`useConnections`), que também alimenta o ponto de saúde do topo; a medição
 * pede uma checagem nova, cujo resultado chega por `ragx:connections`.
 */
/** "3 de 3 conectadas", ou quantas pedem atenção: o resumo que o olho procura primeiro. */
function Overall({ connections }: { connections: ConnectionCheck[] }) {
  const ok = connections.filter((c) => c.state === 'ok').length
  const erro = connections.some((c) => c.state === 'error')
  const tone = ok === connections.length ? 'ok' : erro ? 'error' : 'warn'
  const texto =
    ok === connections.length
      ? `${ok} de ${connections.length} conectadas`
      : `${connections.length - ok} de ${connections.length} ${connections.length - ok === 1 ? 'pede' : 'pedem'} atenção`
  return (
    <p className={`conn-overall-chip conn-overall-${tone}`} role="status">
      <span className="conn-overall-dot" aria-hidden="true" />
      {texto}
    </p>
  )
}

export function ConnectionsPage({
  connections,
  checking,
  onRefresh,
  jobs,
  claude,
}: {
  connections: ConnectionCheck[] | null
  checking: boolean
  onRefresh: () => void
  jobs: readonly JobView[]
  /** Os perfis do Claude Code; sem ele (testes antigos), o card não aparece. */
  claude?: ClaudeToggle
}) {
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Conexões</h1>
          <p className="page-lede">O que o RAGX precisa para funcionar. O painel confere a cada 30 segundos.</p>
        </div>
        <div className="conn-overall">
          {connections !== null && <Overall connections={connections} />}
          <button type="button" className="btn" onClick={onRefresh} disabled={checking}>
            {checking ? 'Verificando…' : 'Verificar agora'}
          </button>
        </div>
      </header>
      <ConnectionGrid
        connections={connections}
        jobs={jobs}
        extra={(c) => (c.id === 'claude' && claude ? <ClaudeProfiles claude={claude} /> : null)}
      />
    </section>
  )
}

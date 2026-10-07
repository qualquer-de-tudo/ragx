import { useEffect, useState } from 'react'
import type { ConnectionCheck, JobView, ProjectSnapshot } from '../types/ragx-bridge'
import { ConnectionsTabs } from '../components/connections/ConnectionsTabs'
import { AutoSetupCard } from '../components/connections/AutoSetupCard'
import { useAutoSetup } from '../hooks/useAutoSetup'
import type { ClaudeToggle } from '../hooks/useClaudeIntegration'

/**
 * Tela Conexões: ambiente CLI/Ollama e abas por agente, cada um
 * com selo, fatos e controles; no Ollama também trocar de
 * modo, parar e medir a velocidade. A checagem mora no `App`
 * (`useConnections`), que também alimenta o ponto de saúde do topo; a medição
 * pede uma checagem nova, cujo resultado chega por `ragx:connections`.
 */
/** Resume a saúde do ambiente comum; agentes são conexões opcionais. */
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
  projects = [],
}: {
  connections: ConnectionCheck[] | null
  checking: boolean
  onRefresh: () => void
  jobs: readonly JobView[]
  /** Os perfis do Claude Code; sem ele (testes antigos), o card não aparece. */
  claude?: ClaudeToggle
  /** Os projetos do último snapshot: o card de ajuste automático conta os hooks de git. */
  projects?: readonly ProjectSnapshot[]
}) {
  const auto = useAutoSetup()
  const [refreshKey, setRefreshKey] = useState(0)
  const ranAt = auto.state?.lastRunAt ?? null
  const refreshClaude = claude?.refresh
  // O ajuste pode ter completado hooks por fora: relê os perfis quando uma rodada nova termina.
  useEffect(() => {
    if (ranAt !== null) refreshClaude?.()
  }, [ranAt, refreshClaude])
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Conexões</h1>
          <p className="page-lede">Seu ambiente e seus agentes, no mesmo lugar. Conecte o RAGX onde você trabalha.</p>
        </div>
        <div className="conn-overall">
          {connections !== null && <Overall connections={connections.filter((c) => c.id !== 'claude')} />}
          <button type="button" className="btn" onClick={() => { onRefresh(); refreshClaude?.(); setRefreshKey((v) => v + 1) }} disabled={checking}>
            {checking ? 'Verificando…' : 'Verificar agora'}
          </button>
        </div>
      </header>
      <ConnectionsTabs
        connections={connections}
        jobs={jobs}
        claude={claude}
        refreshKey={refreshKey}
        claudeExtra={claude ? <AutoSetupCard auto={auto} profiles={claude.profiles} projects={projects} /> : null}
      />
    </section>
  )
}

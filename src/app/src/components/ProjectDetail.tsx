import { useState } from 'react'
import type { ProjectSnapshot, TrialResult, SecurityScanResult } from '../types/ragx-bridge'

interface Props {
  project: ProjectSnapshot | null
}

export function ProjectDetail({ project }: Props) {
  const [trial, setTrial] = useState<TrialResult | 'loading' | { error: string } | null>(null)
  const [scan, setScan] = useState<SecurityScanResult | 'loading' | { error: string } | null>(null)

  async function handleRunTrial() {
    if (!project || !project.path) return
    setTrial('loading')
    try {
      setTrial(await window.ragx.runTrial(project.path))
    } catch (err) {
      setTrial({ error: err instanceof Error ? err.message : String(err) })
    }
  }

  async function handleRunScan() {
    if (!project || !project.path) return
    setScan('loading')
    try {
      setScan(await window.ragx.runSecurityScan(project.path))
    } catch (err) {
      setScan({ error: err instanceof Error ? err.message : String(err) })
    }
  }

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
        <button type="button" onClick={handleRunTrial} disabled={trial === 'loading' || !project.path}>
          {trial === 'loading' ? 'Calculando…' : 'Ver economia estimada'}
        </button>
        {!project.path && (
          <p className="empty-hint">Disponível apenas para projetos clonados localmente.</p>
        )}
        {trial && trial !== 'loading' && !('error' in trial) && (
          <p className="estimate-result">
            Estimativa: {(trial.totals.saved_ratio * 100).toFixed(0)}% de economia ·
            cobertura de fonte {(trial.totals.source_coverage * 100).toFixed(0)}%
          </p>
        )}
        {trial && trial !== 'loading' && 'error' in trial && (
          <p className="warning">Não foi possível calcular agora: {trial.error}</p>
        )}
      </section>

      <section>
        <h2>Segurança</h2>
        <button type="button" onClick={handleRunScan} disabled={scan === 'loading' || !project.path}>
          {scan === 'loading' ? 'Escaneando…' : 'Atualizar achados de segurança'}
        </button>
        {!project.path && (
          <p className="empty-hint">Disponível apenas para projetos clonados localmente.</p>
        )}
        {scan && scan !== 'loading' && !('error' in scan) && (
          <p>{scan.blocked.length} bloqueados · {scan.redacted.length} redigidos</p>
        )}
        {scan && scan !== 'loading' && 'error' in scan && (
          <p className="warning">Não foi possível escanear agora: {scan.error}</p>
        )}
      </section>
    </main>
  )
}

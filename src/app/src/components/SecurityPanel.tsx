import { useId, useState } from 'react'
import type { SecurityScanResult } from '../types/ragx-bridge'
import { readCache, writeScan, type Cached } from '../onDemandCache'
import { formatNumber, formatTime } from '../format'

interface Props {
  projectId: string
  projectPath: string | null
}

type State = Cached<SecurityScanResult> | 'loading' | { error: string } | null

const MAX_LISTED = 8

const SEVERITY: Record<string, { label: string; tone: string; icon: string }> = {
  critical: { label: 'crítico', tone: 'critical', icon: '■' },
  high: { label: 'alto', tone: 'critical', icon: '▲' },
  medium: { label: 'médio', tone: 'warning', icon: '●' },
  low: { label: 'baixo', tone: 'muted', icon: '○' },
}

function fileName(p: string): string {
  return p.split(/[\\/]/).pop() ?? p
}

function dirName(p: string): string {
  return p.split(/[\\/]/).slice(0, -1).join('/')
}

function severityOf(s: string) {
  return SEVERITY[s] ?? { label: s, tone: 'muted', icon: '○' }
}

export function SecurityPanel({ projectId, projectPath }: Props) {
  const titleId = useId()
  const [state, setState] = useState<State>(() => readCache(projectId).scan ?? null)

  async function run() {
    if (!projectPath) return
    setState('loading')
    try {
      setState(writeScan(projectId, await window.ragx.runSecurityScan(projectId)))
    } catch (err) {
      setState({ error: err instanceof Error ? err.message : String(err) })
    }
  }

  const loading = state === 'loading'
  const done = state !== null && state !== 'loading' && 'result' in state ? state : null
  const failed = state !== null && state !== 'loading' && 'error' in state ? state.error : null

  return (
    <section className="card detail-card panel" aria-labelledby={titleId}>
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          Segurança
        </h2>
      </div>
      <p className="dim panel-lede">
        Arquivos com segredos são bloqueados antes de entrar no índice. O scan mostra o que ficou de
        fora e por quê.
      </p>

      {done && <ScanSummary result={done.result} at={done.at} />}
      {failed && <p className="callout callout-error">Não foi possível escanear agora: {failed}</p>}

      <div className="action-row">
        <button type="button" className="btn" onClick={run} disabled={loading || !projectPath}>
          {loading ? 'Escaneando…' : 'Atualizar achados de segurança'}
        </button>
        {!projectPath && <p className="hint">Disponível apenas para projetos clonados localmente.</p>}
      </div>
    </section>
  )
}

function ScanSummary({ result, at }: { result: SecurityScanResult; at: string }) {
  const { blocked, redacted, scanned } = result
  const clean = blocked.length === 0 && redacted.length === 0
  const listed = blocked.slice(0, MAX_LISTED)

  return (
    <div className="scan">
      {clean ? (
        <p className="status-line is-good">
          <span aria-hidden="true">✓</span> Nenhum segredo encontrado em {formatNumber(scanned)} arquivos.
        </p>
      ) : (
        <dl className="pairs">
          <div>
            <dt>Bloqueados</dt>
            <dd className={blocked.length ? 'is-critical' : undefined}>{formatNumber(blocked.length)}</dd>
          </div>
          <div>
            <dt>Com trechos redigidos</dt>
            <dd>{formatNumber(redacted.length)}</dd>
          </div>
          <div>
            <dt>Arquivos verificados</dt>
            <dd>{formatNumber(scanned)}</dd>
          </div>
        </dl>
      )}

      {listed.length > 0 && (
        <ul className="findings">
          {listed.map((b) => {
            const sev = severityOf(b.severity)
            return (
              <li key={`${b.path}:${b.line}:${b.rule}`}>
                <span className={`sev sev-${sev.tone}`}>
                  <span aria-hidden="true">{sev.icon}</span> {sev.label}
                </span>
                <span className="finding-main" title={b.line > 0 ? `${b.path}:${b.line}` : b.path}>
                  <span className="finding-path">
                    <span className="finding-file">
                      {fileName(b.path)}
                      {b.line > 0 && <span className="finding-line">:{b.line}</span>}
                    </span>
                    {dirName(b.path) && <span className="finding-dir">{dirName(b.path)}</span>}
                  </span>
                  <span className="finding-rule">{b.rule}</span>
                </span>
              </li>
            )
          })}
        </ul>
      )}
      {blocked.length > MAX_LISTED && (
        <p className="hint">
          E mais {formatNumber(blocked.length - MAX_LISTED)}. Veja todos com <code>ragx security scan .</code>
        </p>
      )}
      <p className="hint">Escaneado às {formatTime(at)}</p>
    </div>
  )
}

import { useEffect, useId, useRef, useState } from 'react'
import type { ConnectionAction, ConnectionCheck, JobView } from '../../types/ragx-bridge'
import { Badge, type Tone } from '../shell/Badge'
import { activeConnectionJob } from '../../state'
import { enqueueConnectionAction } from '../../jobs'
import { formatRelative } from '../../format'

const BADGE: Record<ConnectionCheck['state'], { tone: Tone; label: string }> = {
  ok: { tone: 'good', label: 'Conectado' },
  warn: { tone: 'warning', label: 'Atenção' },
  error: { tone: 'critical', label: 'Não conectado' },
}

/** Títulos dos três cards antes da primeira checagem (mesma ordem de `checkAll`). */
const PENDING_TITLES = ['RAGX CLI', 'Claude Code', 'Ollama (Docker)'] as const

const COPIED_MS = 2000

/** Bloco mono com o texto de ajuda (às vezes um comando) e um botão para copiar. */
function HelpBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch (err) {
      console.error('copiar falhou:', err)
      return
    }
    setCopied(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopied(false), COPIED_MS)
  }

  return (
    <div className="conn-help">
      <pre className="conn-help-text">{text}</pre>
      <div className="conn-help-foot">
        <span className="hint" role="status">
          {copied ? 'Copiado' : ''}
        </span>
        <button type="button" className="btn btn-quiet btn-sm" onClick={() => void copy()}>
          Copiar
        </button>
      </div>
    </div>
  )
}

function ActionButton({
  action,
  jobs,
  onAction,
}: {
  action: ConnectionAction
  jobs: readonly JobView[]
  onAction: (action: ConnectionAction) => void
}) {
  const active = activeConnectionJob(jobs, action)
  const busy = active === null ? null : active.state === 'running' ? 'Rodando…' : 'Na fila'
  return (
    <button
      type="button"
      className="btn btn-primary btn-block"
      disabled={busy !== null}
      aria-label={busy ? `${action.label}: ${busy.replace('…', '').toLowerCase()}` : undefined}
      onClick={() => onAction(action)}
    >
      {busy ?? action.label}
    </button>
  )
}

/**
 * Card de uma conexão, no estilo dos provedores do Perssua: título, selo,
 * resumo, fatos, ajuda e um botão de largura total por ação. Com tarefa da
 * mesma ação na fila ou rodando, o botão diz isso e fica desabilitado.
 */
export function ConnectionCard({
  check,
  onAction = (a) => void enqueueConnectionAction(a),
  jobs = [],
}: {
  check: ConnectionCheck
  onAction?: (action: ConnectionAction) => void
  jobs?: readonly JobView[]
}) {
  const titleId = useId()
  const badge = BADGE[check.state]
  // O processo principal só manda a data; quem formata é o renderer.
  const facts =
    check.id === 'claude'
      ? [
          ...check.facts,
          {
            label: 'Última chamada MCP',
            value: check.lastMcpCallAt ? formatRelative(check.lastMcpCallAt) : 'nenhuma registrada',
          },
        ]
      : check.facts

  return (
    <article className={`card conn-card conn-${check.state}`} aria-labelledby={titleId}>
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          {check.title}
        </h2>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>
      <p className="conn-summary">{check.summary}</p>
      {facts.length > 0 && (
        <dl className="pairs conn-facts">
          {facts.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {check.help && <HelpBlock text={check.help} />}
      {check.actions.length > 0 && (
        <div className="conn-actions">
          {check.actions.map((a) => (
            <ActionButton key={`${a.kind}|${a.model ?? ''}`} action={a} jobs={jobs} onAction={onAction} />
          ))}
        </div>
      )}
    </article>
  )
}

/** Card neutro enquanto a primeira checagem não voltou: nada de verde antes da hora. */
function PendingCard({ title }: { title: string }) {
  const titleId = useId()
  return (
    <article className="card conn-card" aria-labelledby={titleId} aria-busy="true">
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          {title}
        </h2>
        <Badge tone="muted">Verificando…</Badge>
      </div>
      <p className="conn-summary dim">Conferindo esta conexão.</p>
    </article>
  )
}

/** Grade com os três cards (ou os três neutros antes da primeira checagem). */
export function ConnectionGrid({
  connections,
  jobs,
  onAction,
}: {
  connections: ConnectionCheck[] | null
  jobs: readonly JobView[]
  onAction?: (action: ConnectionAction) => void
}) {
  return (
    <ul className="conn-grid" aria-label="Conexões">
      {connections === null
        ? PENDING_TITLES.map((t) => (
            <li key={t}>
              <PendingCard title={t} />
            </li>
          ))
        : connections.map((c) => (
            <li key={c.id}>
              <ConnectionCard check={c} jobs={jobs} onAction={onAction} />
            </li>
          ))}
    </ul>
  )
}

import { useEffect, useId, useRef, useState } from 'react'
import type { ConnectionAction, ConnectionCheck, JobView } from '../../types/ragx-bridge'
import { Badge, type Tone } from '../shell/Badge'
import { activeConnectionJob, activeOllamaSwitch, jobStateLabel } from '../../state'
import { enqueueConnectionAction, measureOllama } from '../../jobs'
import { formatRelative } from '../../format'

const BADGE: Record<ConnectionCheck['state'], { tone: Tone; label: string }> = {
  ok: { tone: 'good', label: 'Conectado' },
  warn: { tone: 'warning', label: 'Atenção' },
  error: { tone: 'critical', label: 'Não conectado' },
}

/**
 * Títulos dos três cards antes da primeira checagem (mesma ordem de
 * `checkAll`). O do Ollama não diz o modo: só a checagem sabe se é Docker ou
 * local.
 */
const PENDING_TITLES = ['RAGX CLI', 'Claude Code', 'Ollama'] as const

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

/**
 * Botão de uma ação. Principal: azul, largura total. De apoio (`secondary`):
 * neutro e menor, no grupo "Outras ações". Com tarefa do mesmo tipo na fila
 * ou rodando (ou medição em andamento) diz isso e fica desabilitado.
 */
function ActionButton({
  action,
  jobs,
  measuring,
  onAction,
}: {
  action: ConnectionAction
  jobs: readonly JobView[]
  measuring: boolean
  onAction: (action: ConnectionAction) => void
}) {
  const active = activeConnectionJob(jobs, action)
  const isMeasuring = action.kind === 'ollama-benchmark' && measuring
  let busy: { text: string; spoken: string } | null = null
  if (isMeasuring) busy = { text: 'Medindo…', spoken: 'medindo' }
  else if (active !== null) {
    const label = jobStateLabel(active)
    busy = { text: label, spoken: label.toLowerCase() }
  }
  return (
    <button
      type="button"
      className={action.secondary ? 'btn conn-btn-more' : 'btn btn-primary btn-block'}
      disabled={busy !== null}
      aria-busy={isMeasuring || undefined}
      aria-label={busy ? `${action.label}: ${busy.spoken}` : undefined}
      onClick={() => onAction(action)}
    >
      {busy?.text ?? action.label}
    </button>
  )
}

/** Aviso enquanto o Ollama troca de modo: a tarefa é longa e o card muda no meio dela. */
function SwitchNote({ job }: { job: JobView }) {
  return (
    <div className="conn-note" role="status" aria-label="Troca do Ollama em andamento">
      <p className="conn-note-head">
        <strong>{job.label}</strong>
        <span className="conn-note-state">{jobStateLabel(job)}</span>
      </p>
      <p className="conn-note-body">A troca leva alguns minutos; acompanhe pela fila no topo.</p>
    </div>
  )
}

/**
 * Card de uma conexão, no estilo dos provedores do Perssua: título, selo,
 * resumo, fatos, ajuda e as ações. As principais vêm em botões azuis de
 * largura total; as de apoio (medir velocidade, parar o Ollama), num grupo
 * neutro e menor logo abaixo. Com tarefa da mesma ação na fila ou rodando, o
 * botão diz isso e fica desabilitado.
 *
 * "Medir velocidade" não passa por `onAction`: não é tarefa da fila, e o card
 * precisa esperar a medição para mostrar "Medindo…" e o erro, se houver.
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
  const [measuring, setMeasuring] = useState(false)
  const [benchError, setBenchError] = useState<string | null>(null)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  async function measure() {
    if (measuring) return
    setMeasuring(true)
    setBenchError(null)
    const error = await measureOllama()
    if (!alive.current) return
    setBenchError(error)
    setMeasuring(false)
  }

  function act(action: ConnectionAction) {
    if (action.kind === 'ollama-benchmark') void measure()
    else onAction(action)
  }

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
  const switching = check.id === 'ollama' ? activeOllamaSwitch(jobs) : null
  const main = check.actions.filter((a) => !a.secondary)
  const more = check.actions.filter((a) => a.secondary)
  const button = (a: ConnectionAction) => (
    <ActionButton key={`${a.kind}|${a.model ?? ''}`} action={a} jobs={jobs} measuring={measuring} onAction={act} />
  )

  return (
    <article className={`card conn-card conn-${check.state}`} aria-labelledby={titleId}>
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          {check.title}
        </h2>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>
      <p className="conn-summary">{check.summary}</p>
      {switching && <SwitchNote job={switching} />}
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
      {benchError !== null && (
        <p className="callout callout-error conn-callout" role="alert">
          Não foi possível medir: {benchError}
        </p>
      )}
      {check.actions.length > 0 && (
        <div className="conn-actions">
          {main.map(button)}
          {more.length > 0 && (
            <div className="conn-actions-more" role="group" aria-label="Outras ações">
              {more.map(button)}
            </div>
          )}
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

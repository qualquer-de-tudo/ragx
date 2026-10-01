import { useId, useState } from 'react'
import type { SessionGroup } from '../../sessions'
import { formatCompact, formatNumber, formatTime } from '../../format'
import { ActivityRow } from './ActivityRow'

function duration(g: SessionGroup): string {
  const s = Math.round((Date.parse(g.lastAt) - Date.parse(g.startedAt)) / 1000)
  if (s < 60) return `${s} s`
  const m = Math.round(s / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`
}

function who(g: SessionGroup): string {
  const perfil = g.profile ? ` · ${g.profile}` : ''
  return g.client === 'claude-code' ? `Claude Code${perfil}` : 'Agente ou terminal'
}

function header(g: SessionGroup): string {
  const quando = `${formatTime(g.startedAt)} a ${formatTime(g.lastAt)} (${duration(g)})`
  return g.session === null
    ? `${g.projectName} · Sem sessão identificada · ${quando}`
    : `${who(g)} · ${g.projectName} · sessão ${g.session} · ${quando}`
}

function summary(g: SessionGroup): string {
  const parts = [
    `${formatNumber(g.mcpCalls)} chamada(s) MCP`,
    `${formatNumber(g.cliCalls)} comando(s) ragx`,
    `${formatCompact(g.delivered)} tokens entregues`,
    g.usedRagx ? 'usou o RAGX' : 'não chamou o RAGX',
  ]
  if (g.starts > 1) parts.push(`${formatNumber(g.starts)} inícios de contexto (subagentes)`)
  // falha marcada em texto, nunca só por cor ou forma
  parts.push(g.failures === null ? 'falhas: sem dado' : `${formatNumber(g.failures)} falha(s)`)
  return parts.join(', ')
}

/** Faixa de tempo decorativa: um traço por evento, na posição proporcional; falha tem forma própria (traço alto). */
function Strip({ g }: { g: SessionGroup }) {
  const t0 = Date.parse(g.startedAt)
  const span = Math.max(1, Date.parse(g.lastAt) - t0)
  return (
    <span className="session-strip" aria-hidden="true">
      {g.events.map((e) => (
        <span
          key={e.id}
          className={`session-tick${e.ok === false ? ' is-failure' : ''}`}
          style={{ left: `${((Date.parse(e.ts) - t0) / span) * 100}%` }}
        />
      ))}
    </span>
  )
}

function SessionItem({ g }: { g: SessionGroup }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  return (
    <li className="session-item">
      <button type="button" className="session-head" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((v) => !v)}>
        <span className="session-title">{header(g)}</span>
        <span className="session-summary dim">{summary(g)}</span>
        <Strip g={g} />
      </button>
      {open && (
        <ol id={listId} className="activity-feed session-events" aria-label="Eventos da sessão, em ordem cronológica">
          {g.events.map((e) => (
            <ActivityRow key={e.id} event={e} />
          ))}
        </ol>
      )}
    </li>
  )
}

/** Visão "Sessões" da Atividade (RAGX-0188): uma linha por sessão, expansível. */
export function SessionList({ groups }: { groups: readonly SessionGroup[] }) {
  return (
    <ol className="session-list" aria-label="Sessões, da mais recente para a mais antiga">
      {groups.map((g) => (
        <SessionItem key={g.key} g={g} />
      ))}
    </ol>
  )
}

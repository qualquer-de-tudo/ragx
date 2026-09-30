import { useMemo, useState } from 'react'
import type { ActivityEvent, JobView, ProjectSnapshot } from '../types/ragx-bridge'
import {
  FILTER_LABEL,
  LIVE_MS,
  filterEvents,
  totals,
  whatLabel,
  whoLabel,
  type ActivityFilter,
} from '../activity'
import { formatCompact, formatNumber, formatPercent, formatRelative, formatTime } from '../format'
import { Section, Stat } from '../components/shell/Card'
import { sourceLabel } from '../indexSource'

const FILTERS: ActivityFilter[] = ['all', 'mcp', 'cli', 'session']

/** Uma indexação acontecendo agora, pelo snapshot (hook, CLI) ou pela fila do painel. */
interface Running {
  projectId: string
  projectName: string
  what: string
  since: string | null
}

function runningNow(projects: readonly ProjectSnapshot[], jobs: readonly JobView[]): Running[] {
  const out = new Map<string, Running>()
  for (const p of projects) {
    if (p.running) {
      out.set(p.id, { projectId: p.id, projectName: p.name, what: `Indexando · ${sourceLabel(p.running.source)}`, since: p.running.startedAt })
    }
  }
  for (const j of jobs) {
    if (j.state !== 'running' || j.projectId === null || out.has(j.projectId)) continue
    const name = projects.find((p) => p.id === j.projectId)?.name ?? j.projectId
    out.set(j.projectId, { projectId: j.projectId, projectName: name, what: j.label, since: j.startedAt })
  }
  return [...out.values()]
}

function tokensText(e: ActivityEvent): string | null {
  if (e.tokensDelivered === null) return null
  if (e.baselineTokens === null || e.baselineTokens <= 0) return `${formatNumber(e.tokensDelivered)} tokens`
  const saved = 1 - e.tokensDelivered / e.baselineTokens
  return `${formatNumber(e.tokensDelivered)} de ${formatNumber(e.baselineTokens)} tokens (${saved >= 0 ? '−' : '+'}${formatPercent(Math.abs(saved))})`
}

function msText(ms: number | null): string | null {
  if (ms === null) return null
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`
}

const KIND_LABEL: Record<ActivityEvent['kind'], string> = { mcp: 'MCP', cli: 'CLI', session: 'Sessão' }

/**
 * O que os agentes e a CLI estão fazendo nos projetos, ao vivo: chamadas MCP,
 * comandos de consulta no terminal, sessões do Claude abertas e indexações em
 * andamento. Nunca a consulta: o log não a tem, de propósito.
 */
export function ActivityPage({
  events,
  projects,
  jobs,
  now,
  onOpen,
}: {
  events: readonly ActivityEvent[]
  projects: readonly ProjectSnapshot[]
  jobs: readonly JobView[]
  now: number
  onOpen: (projectId: string) => void
}) {
  const [kind, setKind] = useState<ActivityFilter>('all')
  const [projectId, setProjectId] = useState<string | null>(null)

  const shown = useMemo(() => filterEvents(events, kind, projectId), [events, kind, projectId])
  const t = useMemo(() => totals(events), [events])
  const running = runningNow(projects, jobs)
  const live = events.length > 0 && now - Date.parse(events[0].ts) <= LIVE_MS
  const withActivity = useMemo(() => {
    const ids = new Set(events.map((e) => e.projectId))
    return projects.filter((p) => ids.has(p.id)).sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))
  }, [events, projects])
  const economia = t.baseline > 0 ? 1 - t.delivered / t.baseline : null

  return (
    <section className="page activity">
      <header className="page-head">
        <div>
          <h1 className="page-title">Atividade</h1>
          <p className="dim">O que os agentes e a CLI fizeram nos projetos nas últimas 24 h. Atualiza sozinho.</p>
        </div>
        <p className={`live-indicator${live ? ' live-indicator-on' : ''}`} role="status">
          <span className="live-dot" aria-hidden="true" />
          {live ? 'Em uso agora' : 'Ao vivo · nada no último minuto'}
        </p>
      </header>

      <div className="stats stats-4">
        <Stat label="Chamadas MCP" value={formatNumber(t.calls)} note="últimas 24 h" />
        <Stat label="Sessões do Claude" value={formatNumber(t.sessions)} note={`${formatNumber(t.cliCommands)} comando(s) no terminal`} />
        <Stat
          label="Tokens economizados"
          value={formatCompact(Math.max(0, t.baseline - t.delivered))}
          note={economia === null ? 'sem medição ainda' : `${formatPercent(economia)} menos que ler os arquivos`}
        />
        <Stat label="Projetos em uso" value={formatNumber(t.projects)} note={`de ${formatNumber(projects.length)}`} />
      </div>

      {running.length > 0 && (
        <Section title="Em andamento">
          <ul className="running-list">
            {running.map((r) => (
              <li key={r.projectId} className="running-item">
                <span className="live-dot live-dot-on" aria-hidden="true" />
                <button type="button" className="link-button" onClick={() => onOpen(r.projectId)}>
                  {r.projectName}
                </button>
                <span className="dim">{r.what}</span>
                {r.since && <span className="dim running-since">{formatRelative(r.since, new Date(now))}</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Linha do tempo de uso">
        <div className="activity-toolbar">
          <div className="segmented" role="radiogroup" aria-label="Tipo de atividade">
            {FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                role="radio"
                aria-checked={kind === f}
                className="segmented-item"
                onClick={() => setKind(f)}
              >
                {FILTER_LABEL[f]}
              </button>
            ))}
          </div>
          <label className="activity-project-filter">
            <span className="dim">Projeto</span>
            <select value={projectId ?? ''} onChange={(e) => setProjectId(e.target.value || null)}>
              <option value="">Todos</option>
              {withActivity.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {shown.length === 0 ? (
          <p className="dim activity-empty">
            {events.length === 0
              ? 'Nenhuma atividade nas últimas 24 h. Ela aparece aqui assim que um agente usar o RAGX por MCP, alguém rodar ragx search ou ragx context no terminal, ou uma sessão do Claude Code abrir num projeto indexado.'
              : 'Nada com esse filtro nas últimas 24 h.'}
          </p>
        ) : (
          <ol className="activity-feed" aria-label="Eventos, do mais novo para o mais antigo">
            {shown.map((e) => {
              const fresh = now - Date.parse(e.ts) < 5000
              const detalhes = [tokensText(e), msText(e.ms), e.ok === false ? 'falhou' : null].filter(Boolean)
              return (
                <li key={e.id} className={`activity-item${fresh ? ' activity-item-fresh' : ''}`}>
                  <time className="activity-time mono" dateTime={e.ts} title={new Date(e.ts).toLocaleString('pt-BR')}>
                    {formatTime(e.ts)}
                  </time>
                  <span className={`activity-kind activity-kind-${e.kind}`}>{KIND_LABEL[e.kind]}</span>
                  <span className="activity-main">
                    <span className="activity-what mono">{whatLabel(e)}</span>
                    <span className="dim"> em </span>
                    <button type="button" className="link-button" onClick={() => onOpen(e.projectId)}>
                      {e.projectName}
                    </button>
                  </span>
                  <span className="activity-who">{whoLabel(e)}</span>
                  <span className={`activity-meta dim${e.ok === false ? ' is-critical' : ''}`}>{detalhes.join(' · ')}</span>
                </li>
              )
            })}
          </ol>
        )}
      </Section>
    </section>
  )
}

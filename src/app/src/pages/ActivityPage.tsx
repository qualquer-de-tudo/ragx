import { useMemo, useState } from 'react'
import type { ActivityEvent, JobView, ProjectSnapshot } from '../types/ragx-bridge'
import {
  FILTER_LABEL,
  ACTIVITY_MAX,
  LIVE_MS,
  filterEvents,
  totals,
  type ActivityFilter,
} from '../activity'
import { formatCompact, formatNumber, formatPercent, formatRelative } from '../format'
import { Section, Stat } from '../components/shell/Card'
import { sourceLabel } from '../indexSource'
import { useClock } from '../hooks/useClock'
import { usePricing } from '../hooks/usePricing'
import { formatMoney, savedMoney } from '../money'
import { EmptyState } from '../components/ui/EmptyState'
import { Segmented } from '../components/ui/Segmented'
import { Pager } from '../components/ui/Pager'
import { EVENTS_PER_PAGE, SESSIONS_PER_PAGE, clampPage } from '../paging'
import { ActivityRow } from '../components/activity/ActivityRow'
import { SessionList } from '../components/activity/SessionList'
import { groupSessions } from '../sessions'
import { AdoptionSection } from '../components/activity/AdoptionSection'
import { useAdoption } from '../hooks/useAdoption'

type ActivityView = 'eventos' | 'sessoes'

/** A visão escolhida vale até fechar o painel (como `listPrefs`): o padrão é o feed de sempre. */
let activityViewPref: ActivityView = 'eventos'

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

/**
 * O que os agentes e a CLI estão fazendo nos projetos, ao vivo: chamadas MCP,
 * comandos de consulta no terminal, sessões do Claude abertas e indexações em
 * andamento. Nunca a consulta: o log não a tem, de propósito.
 */
export function ActivityPage({
  events,
  projects,
  jobs,
  now: nowProp,
  onOpen,
}: {
  events: readonly ActivityEvent[]
  projects: readonly ProjectSnapshot[]
  jobs: readonly JobView[]
  /** Instante fixo (testes); sem ele a página assina o relógio de 5 s. */
  now?: number
  onOpen: (projectId: string) => void
}) {
  const clock = useClock(5000)
  const now = nowProp ?? clock
  const [kind, setKind] = useState<ActivityFilter>('all')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [view, setViewState] = useState<ActivityView>(activityViewPref)
  const [page, setPage] = useState(0)
  const setView = (v: ActivityView) => {
    activityViewPref = v // lembrada enquanto o painel estiver aberto
    setViewState(v)
    setPage(0)
  }
  // Trocar o filtro volta à primeira página: a lista é outra.
  const changeKind = (k: ActivityFilter) => {
    setKind(k)
    setPage(0)
  }
  const changeProject = (id: string | null) => {
    setProjectId(id)
    setPage(0)
  }

  const shown = useMemo(() => filterEvents(events, kind, projectId), [events, kind, projectId])
  const t = useMemo(() => totals(events), [events])
  const adoption = useAdoption(events)
  const sessions = useMemo(() => (view === 'sessoes' ? groupSessions(shown) : []), [view, shown])
  const pageSize = view === 'sessoes' ? SESSIONS_PER_PAGE : EVENTS_PER_PAGE
  const total = view === 'sessoes' ? sessions.length : shown.length
  const current = clampPage(page, total, pageSize)
  const pageEvents = useMemo(() => shown.slice(current * pageSize, (current + 1) * pageSize), [shown, current, pageSize])
  const pageSessions = useMemo(() => sessions.slice(current * pageSize, (current + 1) * pageSize), [sessions, current, pageSize])
  const running = runningNow(projects, jobs)
  const live = events.length > 0 && now - Date.parse(events[0].ts) <= LIVE_MS
  const withActivity = useMemo(() => {
    const ids = new Set(events.map((e) => e.projectId))
    return projects.filter((p) => ids.has(p.id)).sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))
  }, [events, projects])
  const economia = t.baseline > 0 ? 1 - t.delivered / t.baseline : null
  const { pricing } = usePricing()
  const money =
    pricing && economia !== null ? formatMoney(savedMoney(t.baseline - t.delivered, pricing.perMTokInput), pricing.currency) : null

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
          note={
            economia === null
              ? 'sem medição ainda'
              : `${formatPercent(economia)} menos que ler os arquivos${money ? ` · ${money} (estimativa)` : ''}`
          }
        />
        <Stat label="Projetos em uso" value={formatNumber(t.projects)} note={`de ${formatNumber(projects.length)}`} />
      </div>

      {adoption && <AdoptionSection adoption={adoption} />}

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
        <Segmented
          label="Visão"
          value={view}
          options={[
            { value: 'eventos', label: 'Eventos' },
            { value: 'sessoes', label: 'Sessões' },
          ]}
          onChange={setView}
        />
        <div className="activity-toolbar">
          <Segmented
            label="Tipo de atividade"
            value={kind}
            options={FILTERS.map((f) => ({ value: f, label: FILTER_LABEL[f] }))}
            onChange={changeKind}
          />
          <label className="activity-project-filter">
            <span className="dim">Projeto</span>
            <select value={projectId ?? ''} onChange={(e) => changeProject(e.target.value || null)}>
              <option value="">Todos</option>
              {withActivity.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {events.length >= ACTIVITY_MAX && view === 'sessoes' && (
          <p className="hint" role="status">
            Mostrando os {ACTIVITY_MAX} eventos mais recentes; sessões antigas podem estar incompletas.
          </p>
        )}

        {shown.length === 0 ? (
          <EmptyState className="dim activity-empty">
            {events.length === 0
              ? 'Nenhuma atividade nas últimas 24 h. Ela aparece aqui assim que um agente usar o RAGX por MCP, alguém rodar ragx search ou ragx context no terminal, ou uma sessão do Claude Code abrir num projeto indexado.'
              : 'Nada com esse filtro nas últimas 24 h.'}</EmptyState>
        ) : view === 'sessoes' ? (
          <SessionList groups={pageSessions} />
        ) : (
          <ol className="activity-feed" aria-label="Eventos, do mais novo para o mais antigo">
            {pageEvents.map((e) => (
              <ActivityRow key={e.id} event={e} fresh={current === 0 && now - Date.parse(e.ts) < 5000} onOpen={onOpen} />
            ))}
          </ol>
        )}
        {shown.length > 0 && (
          <Pager total={total} page={current} pageSize={pageSize} onPage={setPage} noun={view === 'sessoes' ? 'sessões' : 'eventos'} />
        )}
      </Section>
    </section>
  )
}

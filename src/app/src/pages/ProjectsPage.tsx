import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { JobKind, JobView, ProjectSnapshot } from '../types/ragx-bridge'
import {
  STATE_ACTION,
  activeJobFor,
  busyProjectIds,
  deriveProjectState,
  hasProblem,
  isOutdated,
  lastFailureFor,
  type ProjectState,
} from '../state'
import { commonBase, foldForSearch, formatCompact, formatNumber, formatPercent, parentHint } from '../format'
import { ProjectCard } from '../components/project/ProjectCard'
import { AddProjectDialog } from '../components/project/AddProjectDialog'
import { ProjectActionButton } from '../components/project/ProjectBits'
import { Badge } from '../components/shell/Badge'
import { LivePill } from '../components/shell/LivePill'
import { RelativeTime } from '../components/shell/RelativeTime'
import { Stat } from '../components/shell/Card'
import { STATE_LABEL, STATE_TONE } from '../state'
import { SORT_LABEL, listPrefs, needsAttention, savingsRatio, sortRows, tokensSaved, type ListView, type SortKey } from '../projectMetrics'

type Filter = 'all' | 'outdated' | 'problem'

const FILTERS: Array<{ id: Filter; label: string; test: (s: ProjectState) => boolean }> = [
  { id: 'all', label: 'Todos', test: () => true },
  { id: 'outdated', label: 'Defasados', test: isOutdated },
  { id: 'problem', label: 'Com problema', test: hasProblem },
]

/** Controle segmentado com semântica de grupo de rádio: setas mudam a escolha. */
function SegmentedFilter({
  value,
  counts,
  onChange,
}: {
  value: Filter
  counts: Record<Filter, number>
  onChange: (f: Filter) => void
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (index + 1) % FILTERS.length
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (index - 1 + FILTERS.length) % FILTERS.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = FILTERS.length - 1
    else return
    e.preventDefault()
    onChange(FILTERS[next].id)
    refs.current[next]?.focus()
  }

  return (
    <div className="segmented" role="radiogroup" aria-label="Filtrar projetos">
      {FILTERS.map((f, i) => {
        const checked = f.id === value
        return (
          <button
            key={f.id}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            className="segmented-item"
            onClick={() => onChange(f.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {f.label} ({counts[f.id]})
          </button>
        )
      })}
    </div>
  )
}

/** Tarefa ativa do tipo da ação do botão do card (`null` quando a ação só abre o detalhe). */
function activeAction(jobs: readonly JobView[], projectId: string, state: ProjectState): JobView | null {
  const action = STATE_ACTION[state]
  if (action === null || action.kind === 'open') return null
  return activeJobFor(jobs, projectId, [action.kind])
}

const NOTICE_MS = 4000
const NOTICE_ERROR_MS = 8000

/** Aviso discreto da página: some sozinho; o timer é limpo ao desmontar. */
function useNotice() {
  const [notice, setNotice] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current)
    },
    [],
  )
  // Estável: entra nos `useCallback` dos handlers das linhas (que são `memo`).
  const show = useCallback((text: string, ms: number) => {
    if (timer.current !== null) clearTimeout(timer.current)
    setNotice(text)
    timer.current = setTimeout(() => {
      timer.current = null
      setNotice(null)
    }, ms)
  }, [])
  return { notice, show }
}

/** Linha da lista. `memo`: só renderiza quando o projeto dela, a tarefa ou o estado mudam. */
const ProjectRow = memo(function ProjectRow({
  project,
  state,
  hint,
  active,
  live,
  onOpen,
  onAction,
}: {
  project: ProjectSnapshot
  state: ProjectState
  hint: string | null
  active: JobView | null
  live: boolean
  onOpen: (id: string) => void
  onAction: (project: ProjectSnapshot, kind: JobKind) => void
}) {
  const ratio = savingsRatio(project)
  return (
    <tr>
      <th scope="row">
        <button type="button" className="link-button" onClick={() => onOpen(project.id)}>
          {project.name}
        </button>
        {live && <LivePill />}
        <span className="projects-table-hint dim">{hint ?? 'sem dados'}</span>
      </th>
      <td>
        <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
      </td>
      <td className="num">{ratio === null ? 'sem uso' : formatPercent(ratio)}</td>
      <td className="num">{formatNumber(project.telemetry.totalCalls)}</td>
      <td className="num">{project.counts ? formatCompact(project.counts.documents) : 'sem dados'}</td>
      <td className="dim">{project.index ? <RelativeTime iso={project.index.finishedAt} /> : 'não indexado'}</td>
      <td className="projects-table-action">
        <ProjectActionButton
          project={project}
          state={state}
          active={active}
          onOpen={() => onOpen(project.id)}
          onAction={(kind) => onAction(project, kind)}
        />
      </td>
    </tr>
  )
})

export function ProjectsPage({
  projects,
  jobs,
  query,
  liveIds,
  onOpen,
}: {
  projects: ProjectSnapshot[]
  jobs: JobView[]
  query: string
  /** Projetos com atividade no último minuto (tela de atividade). */
  liveIds?: ReadonlySet<string>
  onOpen: (id: string) => void
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSortState] = useState<SortKey>(listPrefs.sort)
  const [view, setViewState] = useState<ListView>(listPrefs.view)
  const setSort = (k: SortKey) => {
    setSortState(k)
    listPrefs.setSort(k)
  }
  const setView = (v: ListView) => {
    setViewState(v)
    listPrefs.setView(v)
  }
  const [adding, setAdding] = useState(false)
  const { notice, show } = useNotice()

  // A fila mais recente, lida só quando o clique acontece: o handler não troca a cada push de tarefas.
  const jobsRef = useRef(jobs)
  useEffect(() => {
    jobsRef.current = jobs
  }, [jobs])

  const queueAction = useCallback(
    (project: ProjectSnapshot, kind: JobKind) => {
      const label = STATE_ACTION[deriveProjectState(project, busyProjectIds(jobsRef.current))]?.label ?? kind
      window.ragx.enqueueJob({ kind, projectId: project.id }).then(
        () => show(`Adicionado à fila: ${label} em ${project.name}`, NOTICE_MS),
        (err: unknown) => {
          console.error(`enqueueJob(${kind}) falhou:`, err)
          show(`Não foi possível adicionar à fila: ${err instanceof Error ? err.message : String(err)}`, NOTICE_ERROR_MS)
        },
      )
      },
    [show],
  )

  const rows = useMemo(() => {
    const busy = busyProjectIds(jobs)
    const base = commonBase(projects.map((p) => p.path))
    return projects.map((project) => ({
      project,
      state: deriveProjectState(project, busy),
      hint: parentHint(project.path, base),
      job: jobs.find((j) => j.projectId === project.id && j.state === 'running') ?? null,
      failure: lastFailureFor(jobs, project.id),
    }))
  }, [projects, jobs])

  const q = foldForSearch(query.trim())
  const searched = q ? rows.filter((r) => foldForSearch(`${r.project.name}\n${r.project.path ?? ''}`).includes(q)) : rows
  // Contadores seguem a busca: "Defasados (2)" mostra dois cards ao clicar.
  const counts = Object.fromEntries(
    FILTERS.map((f) => [f.id, searched.filter((r) => f.test(r.state)).length]),
  ) as Record<Filter, number>
  const test = FILTERS.find((f) => f.id === filter)!.test
  const shown = sortRows(searched.filter((r) => test(r.state)), sort)

  // Resumo de todos os projetos (não da busca): é a foto do hub inteiro.
  const resumo = {
    chamadas: projects.reduce((n, p) => n + p.telemetry.totalCalls, 0),
    economizados: projects.reduce((n, p) => n + tokensSaved(p), 0),
    atencao: rows.filter((r) => needsAttention(r.state)).length,
  }

  return (
    <section className="page">
      <header className="page-head">
        <h1 className="page-title">Projetos</h1>
        <SegmentedFilter value={filter} counts={counts} onChange={setFilter} />
      </header>

      {projects.length > 0 && (
        <div className="stats stats-4 projects-summary" aria-label="Resumo dos projetos">
          <Stat label="Projetos" value={formatNumber(projects.length)} />
          <Stat label="Chamadas MCP" value={formatNumber(resumo.chamadas)} note="últimas 24 h" />
          <Stat label="Tokens economizados" value={formatCompact(resumo.economizados)} note="últimos 14 dias" />
          <Stat
            label="Pedem atenção"
            value={formatNumber(resumo.atencao)}
            note={resumo.atencao === 0 ? 'tudo em dia' : 'defasados ou com problema'}
          />
        </div>
      )}

      <div className="projects-toolbar">
        <label className="projects-sort">
          <span className="dim">Ordenar por</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <div className="segmented" role="radiogroup" aria-label="Visualização">
          {(['grade', 'lista'] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={view === v}
              className="segmented-item"
              onClick={() => setView(v)}
            >
              {v === 'grade' ? 'Grade' : 'Lista'}
            </button>
          ))}
        </div>
      </div>

      {view === 'lista' ? (
        <>
          <button type="button" className="btn projects-add-inline" onClick={() => setAdding(true)}>
            + Adicionar projeto
          </button>
          {shown.length > 0 && (
            <div className="projects-table-wrap">
              <table className="projects-table">
                <thead>
                  <tr>
                    <th scope="col">Projeto</th>
                    <th scope="col">Estado</th>
                    <th scope="col" className="num">Economia</th>
                    <th scope="col" className="num">Chamadas 24 h</th>
                    <th scope="col" className="num">
                      <abbr title="Documentos">Docs</abbr>
                    </th>
                    <th scope="col">Indexado</th>
                    <th scope="col">
                      <span className="sr-only">Ação</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <ProjectRow
                      key={r.project.id}
                      project={r.project}
                      state={r.state}
                      hint={r.hint}
                      active={activeAction(jobs, r.project.id, r.state)}
                      live={liveIds?.has(r.project.id) ?? false}
                      onOpen={onOpen}
                      onAction={queueAction}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
      <ul className="project-grid" aria-label="Projetos">
        <li>
          <button type="button" className="add-card" onClick={() => setAdding(true)}>
            <span className="add-card-plus" aria-hidden="true">
              +
            </span>
            <span className="add-card-title">Adicionar projeto</span>
            <span className="add-card-sub">Escolha uma pasta; o RAGX encontra os projetos dentro dela</span>
          </button>
        </li>
        {shown.map((r) => (
          <li key={r.project.id}>
            <ProjectCard
              project={r.project}
              state={r.state}
              hint={r.hint}
              job={r.job}
              active={activeAction(jobs, r.project.id, r.state)}
              failure={r.failure}
              live={liveIds?.has(r.project.id) ?? false}
              onOpen={onOpen}
              onAction={queueAction}
            />
          </li>
        ))}
      </ul>
      )}

      {shown.length === 0 && (
        <p className="empty" role="status">
          Nenhum projeto neste filtro.
        </p>
      )}

      <div className="page-notice" role="status" aria-live="polite">
        {notice}
      </div>

      <AddProjectDialog open={adding} onClose={() => setAdding(false)} />
    </section>
  )
}

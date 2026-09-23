import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
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
import { commonBase, foldForSearch, parentHint } from '../format'
import { ProjectCard } from '../components/project/ProjectCard'
import { AddProjectDialog } from '../components/project/AddProjectDialog'

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
  const show = (text: string, ms: number) => {
    if (timer.current !== null) clearTimeout(timer.current)
    setNotice(text)
    timer.current = setTimeout(() => {
      timer.current = null
      setNotice(null)
    }, ms)
  }
  return { notice, show }
}

export function ProjectsPage({
  projects,
  jobs,
  query,
  onOpen,
}: {
  projects: ProjectSnapshot[]
  jobs: JobView[]
  query: string
  onOpen: (id: string) => void
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [adding, setAdding] = useState(false)
  const { notice, show } = useNotice()

  const queueAction = (project: ProjectSnapshot, kind: JobKind) => {
    const label = STATE_ACTION[deriveProjectState(project, busyProjectIds(jobs))]?.label ?? kind
    window.ragx.enqueueJob({ kind, projectId: project.id }).then(
      () => show(`Adicionado à fila: ${label} em ${project.name}`, NOTICE_MS),
      (err: unknown) => {
        console.error(`enqueueJob(${kind}) falhou:`, err)
        show(`Não foi possível adicionar à fila: ${err instanceof Error ? err.message : String(err)}`, NOTICE_ERROR_MS)
      },
    )
  }

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
  const shown = searched.filter((r) => test(r.state))

  return (
    <section className="page">
      <header className="page-head">
        <h1 className="page-title">Projetos</h1>
        <SegmentedFilter value={filter} counts={counts} onChange={setFilter} />
      </header>

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
              onOpen={onOpen}
              onAction={(kind) => queueAction(r.project, kind)}
            />
          </li>
        ))}
      </ul>

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

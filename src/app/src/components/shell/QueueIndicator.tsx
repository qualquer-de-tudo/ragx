import { useEffect, useId, useRef, useState } from 'react'
import type { JobState, JobView } from '../../types/ragx-bridge'
import { formatEta, formatNumber } from '../../format'
import { Badge, type Tone } from './Badge'

const STATE: Record<JobState, { label: string; tone: Tone }> = {
  queued: { label: 'Na fila', tone: 'muted' },
  running: { label: 'Rodando', tone: 'accent' },
  done: { label: 'Concluída', tone: 'good' },
  failed: { label: 'Falhou', tone: 'critical' },
  cancelled: { label: 'Cancelada', tone: 'muted' },
}

const PHASE: Record<string, string> = {
  scan: 'Lendo arquivos',
  chunk: 'Separando em trechos',
  embed: 'Gerando embeddings',
}

/** Quantas tarefas já encerradas continuam visíveis na lista. */
const FINISHED_SHOWN = 8

const isActive = (j: JobView) => j.state === 'queued' || j.state === 'running'

function triggerText(active: number): string {
  if (active === 0) return 'Nenhuma tarefa'
  return active === 1 ? '1 tarefa' : `${active} tarefas`
}

/** Ativas primeiro (na ordem da fila), depois as encerradas mais recentes. */
function ordered(jobs: JobView[]): JobView[] {
  const finished = jobs
    .filter((j) => !isActive(j))
    .sort((a, b) => (b.finishedAt ?? b.queuedAt).localeCompare(a.finishedAt ?? a.queuedAt))
    .slice(0, FINISHED_SHOWN)
  return [...jobs.filter(isActive), ...finished]
}

function JobItem({ job, onCancel }: { job: JobView; onCancel: (id: string) => void }) {
  const labelId = useId()
  const state = STATE[job.state]
  const running = job.state === 'running'
  const total = running && job.total !== null && job.total > 0 ? job.total : null
  const done = Math.min(job.done ?? 0, total ?? 0)

  const meta: string[] = []
  if (running && job.steps > 1) meta.push(`Passo ${job.step} de ${job.steps}`)
  if (running && job.phase) meta.push(PHASE[job.phase] ?? job.phase)
  if (total !== null) meta.push(`${formatNumber(done)} de ${formatNumber(total)}`)

  return (
    <li className="job">
      <div className="job-head">
        <span className="job-label" id={labelId}>
          {job.label}
        </span>
        <Badge tone={state.tone}>{state.label}</Badge>
      </div>

      {total !== null && (
        <div
          className="progress"
          role="progressbar"
          aria-labelledby={labelId}
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
        >
          <div className="progress-fill" style={{ width: `${(done / total) * 100}%` }} />
        </div>
      )}

      {meta.length > 0 && <p className="job-meta">{meta.join(' · ')}</p>}
      {running && job.etaSeconds !== null && <p className="job-meta">Faltam {formatEta(job.etaSeconds)}</p>}
      {job.note && <p className="job-note">{job.note}</p>}
      {job.error && <p className="job-error">{job.error}</p>}

      {isActive(job) && (
        <div className="job-actions">
          <button type="button" className="btn btn-quiet btn-sm" aria-describedby={labelId} onClick={() => onCancel(job.id)}>
            Cancelar
          </button>
        </div>
      )}
    </li>
  )
}

/**
 * Indicador da fila no topo: mostra quantas tarefas estão ativas e, ao abrir,
 * a lista com estado, progresso e previsão. Não é modal: clicar fora ou Esc
 * fecha, e o foco volta ao botão.
 */
export function QueueIndicator({ jobs, onCancel }: { jobs: JobView[]; onCancel: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const panelId = useId()

  const active = jobs.filter(isActive)
  const running = active.some((j) => j.state === 'running')
  const list = ordered(jobs)

  useEffect(() => {
    if (!open) return
    panelRef.current?.focus()
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  function close() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  return (
    <div className="queue" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`topbar-button queue-trigger${active.length > 0 ? ' is-busy' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        {running ? (
          <span className="spinner" aria-hidden="true" />
        ) : (
          <svg
            className="queue-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            aria-hidden="true"
            focusable="false"
          >
            <path d="M5 7h14M5 12h14M5 17h9" />
          </svg>
        )}
        {triggerText(active.length)}
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          className="popover queue-panel"
          role="dialog"
          aria-label="Tarefas"
          tabIndex={-1}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.stopPropagation()
              close()
            }
          }}
        >
          <div className="popover-head">
            <h2 className="popover-title">Tarefas</h2>
            <span className="popover-sub">Uma por vez, na ordem em que foram pedidas</span>
          </div>
          {list.length === 0 ? (
            <p className="popover-empty">Nada na fila. As tarefas que você pedir no painel aparecem aqui.</p>
          ) : (
            <ul className="job-list">
              {list.map((job) => (
                <JobItem key={job.id} job={job} onCancel={onCancel} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

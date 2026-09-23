import { useState } from 'react'
import type { ProjectSnapshot } from '../types/ragx-bridge'
import { commonBase, formatCompact, formatTime, parentHint } from '../format'
import { deriveProjectState, STATE_LABEL } from '../state'

interface Props {
  projects: ProjectSnapshot[]
  selectedId: string | null
  onSelect: (id: string) => void
  loading?: boolean
  updatedAt?: string | null
}

const FILTER_THRESHOLD = 6
// Sem fila de tarefas nesta tarefa (Task 5) - nenhum projeto está "ocupado"
// pelo lado do renderer ainda; o estado "indexing" ainda pode vir do próprio
// status.json (`p.running`).
const NO_BUSY_IDS = new Set<string>()

function chunksOf(p: ProjectSnapshot): number | null {
  return p.counts?.chunks ?? null
}

export function ProjectList({ projects, selectedId, onSelect, loading = false, updatedAt = null }: Props) {
  const [query, setQuery] = useState('')

  const needle = query.trim().toLowerCase()
  const visible = needle
    ? projects.filter((p) => `${p.name} ${p.path ?? ''}`.toLowerCase().includes(needle))
    : projects
  const largest = Math.max(1, ...projects.map((p) => chunksOf(p) ?? 0))
  const base = commonBase(projects.map((p) => p.path))

  return (
    <aside className="sidebar" aria-label="Projetos">
      <header className="sidebar-head">
        <p className="brand">RAGX</p>
        <p className="sidebar-sub">
          {loading ? 'Lendo o hub…' : projects.length === 1 ? '1 projeto no hub' : `${projects.length} projetos no hub`}
        </p>
      </header>

      {projects.length > FILTER_THRESHOLD && (
        <input
          className="filter"
          type="search"
          placeholder="Filtrar projetos"
          aria-label="Filtrar projetos"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      )}

      {loading ? null : projects.length === 0 ? (
        <div className="sidebar-empty">
          <p>Nenhum projeto no hub ainda.</p>
          <p>
            Rode <code>ragx project register &lt;caminho&gt;</code> num projeto já indexado, ou{' '}
            <code>ragx init</code> num projeto novo.
          </p>
        </div>
      ) : visible.length === 0 ? (
        <p className="sidebar-empty">Nenhum projeto corresponde a “{query}”.</p>
      ) : (
        <ul className="project-list">
          <li className="list-head" aria-hidden="true">
            <span>Projeto</span>
            <span>Chunks</span>
          </li>
          {visible.map((p) => {
            const chunks = chunksOf(p)
            const hint = parentHint(p.path, base)
            const selected = p.id === selectedId
            const state = deriveProjectState(p, NO_BUSY_IDS)
            return (
              <li key={p.id}>
                <button
                  type="button"
                  className={selected ? 'project-item selected' : 'project-item'}
                  aria-current={selected ? 'true' : undefined}
                  onClick={() => onSelect(p.id)}
                >
                  <span className="item-top">
                    <span className="item-name">{p.name}</span>
                    <span className="item-count">{chunks === null ? 'sem dados' : formatCompact(chunks)}</span>
                  </span>
                  <span className="item-bottom">
                    <span className="item-hint">{hint ?? 'só federação'}</span>
                    {state !== 'ok' && (
                      <span className={`item-status status-${state}`}>{STATE_LABEL[state]}</span>
                    )}
                  </span>
                  <span className="item-bar" aria-hidden="true">
                    {chunks !== null && chunks > 0 && (
                      <span style={{ width: `${Math.max(2, (chunks / largest) * 100)}%` }} />
                    )}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}

      <footer className="sidebar-foot">
        {updatedAt ? `Atualizado às ${formatTime(updatedAt)}` : 'Aguardando a primeira leitura'}
      </footer>
    </aside>
  )
}

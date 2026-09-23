import type { ProjectSnapshot } from '../types/ragx-bridge'

interface Props {
  projects: ProjectSnapshot[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ProjectList({ projects, selectedId, onSelect }: Props) {
  if (projects.length === 0) {
    return (
      <aside className="project-list">
        <p className="empty-hint">
          Nenhum projeto no hub ainda. Rode <code>ragx project register &lt;caminho&gt;</code> num
          projeto já indexado.
        </p>
      </aside>
    )
  }

  return (
    <aside className="project-list">
      <ul>
        {projects.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className={p.id === selectedId ? 'selected' : ''}
              onClick={() => onSelect(p.id)}
            >
              <span className="name">{p.name}</span>
              <span className={`status status-${p.status}`}>{p.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}

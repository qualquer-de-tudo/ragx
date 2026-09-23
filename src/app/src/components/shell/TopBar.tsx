import type { JobView, Snapshot } from '../../types/ragx-bridge'
import { QueueIndicator } from './QueueIndicator'

export type Health = NonNullable<Snapshot['connectionsHealth']> | null

const HEALTH: Record<'ok' | 'warn' | 'error' | 'unknown', { label: string; state: string | null }> = {
  ok: { label: 'Conexões: tudo certo', state: null },
  warn: { label: 'Conexões: atenção', state: 'atenção' },
  error: { label: 'Conexões: com problema', state: 'com problema' },
  // Antes da primeira checagem não há dado: nada de "tudo certo" otimista.
  unknown: { label: 'Conexões: verificando', state: null },
}

export function TopBar({
  query,
  onQuery,
  jobs,
  health,
  onOpenConnections,
  onCancelJob,
}: {
  query: string
  onQuery: (query: string) => void
  jobs: JobView[]
  health: Health
  onOpenConnections: () => void
  onCancelJob: (id: string) => void
}) {
  const key = health ?? 'unknown'
  const h = HEALTH[key]

  return (
    <header className="topbar">
      <div className="search">
        <svg
          className="search-icon"
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
          <circle cx="11" cy="11" r="6.5" />
          <path d="m16 16 4 4" />
        </svg>
        <input
          type="search"
          className="search-input"
          placeholder="Buscar projeto"
          aria-label="Buscar projeto"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          spellCheck={false}
          autoComplete="off"
        />
      </div>

      <div className="topbar-end">
        <QueueIndicator jobs={jobs} onCancel={onCancelJob} />
        {/* O texto visível começa por "Conexões" e diz o estado quando algo
            não está bem, então a cor do ponto nunca é o único sinal. */}
        <button
          type="button"
          className={`topbar-button health health-${key}`}
          aria-label={h.label}
          title={h.label}
          onClick={onOpenConnections}
        >
          <span className="health-dot" aria-hidden="true" />
          Conexões
          {h.state && <span className="health-state">{h.state}</span>}
        </button>
      </div>
    </header>
  )
}

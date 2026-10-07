import type { JobView, Snapshot } from '../../types/ragx-bridge'
import { QueueIndicator } from './QueueIndicator'
import { Icon } from '../ui/Icon'
import { Tooltip } from '../ui/Tooltip'

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
      <div className="topbar-inner">
      <div className="search">
        <Icon name="search" className="search-icon" />
        <input
          id="topbar-search"
          type="search"
          className="search-input"
          placeholder="Buscar projeto"
          aria-label="Buscar projeto"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          spellCheck={false}
          autoComplete="off"
        />
        <kbd className="search-kbd" aria-hidden="true">
          Ctrl K
        </kbd>
      </div>

      <div className="topbar-end">
        <QueueIndicator jobs={jobs} onCancel={onCancelJob} />
        {/* O texto visível começa por "Conexões" e diz o estado quando algo
            não está bem, então a cor do ponto nunca é o único sinal. */}
        <Tooltip text={h.label}>
          {(tip) => (
            <button
              type="button"
              className={`topbar-button health health-${key}`}
              aria-label={h.label}
              {...tip}
              onClick={onOpenConnections}
            >
              <span className="health-dot" aria-hidden="true" />
              <span className="topbar-collapse">Conexões</span>
              {h.state && <span className="health-state">{h.state}</span>}
            </button>
          )}
        </Tooltip>
      </div>
      </div>
    </header>
  )
}

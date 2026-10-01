import type { ClaudeToggle } from '../../hooks/useClaudeIntegration'
import type { JobView, Snapshot } from '../../types/ragx-bridge'
import { QueueIndicator } from './QueueIndicator'
import { Icon } from '../ui/Icon'
import { SwitchButton, SwitchTrack } from '../ui/Switch'
import { Tooltip } from '../ui/Tooltip'

export type Health = NonNullable<Snapshot['connectionsHealth']> | null

const HEALTH: Record<'ok' | 'warn' | 'error' | 'unknown', { label: string; state: string | null }> = {
  ok: { label: 'Conexões: tudo certo', state: null },
  warn: { label: 'Conexões: atenção', state: 'atenção' },
  error: { label: 'Conexões: com problema', state: 'com problema' },
  // Antes da primeira checagem não há dado: nada de "tudo certo" otimista.
  unknown: { label: 'Conexões: verificando', state: null },
}

function claudeTitle(claude: ClaudeToggle): string {
  if (claude.error) return claude.error
  if (claude.enabled === null) return 'Verificando o RAGX no Claude Code…'
  const state = claude.enabled ? 'Ligado: o Claude Code usa o RAGX.' : 'Desligado: o Claude Code roda sem o RAGX.'
  return `${state} Vale para todos os projetos, a partir da próxima sessão do Claude Code.`
}

export function TopBar({
  query,
  onQuery,
  jobs,
  health,
  claude,
  onOpenConnections,
  onCancelJob,
}: {
  query: string
  onQuery: (query: string) => void
  jobs: JobView[]
  health: Health
  claude: ClaudeToggle
  onOpenConnections: () => void
  onCancelJob: (id: string) => void
}) {
  const key = health ?? 'unknown'
  const h = HEALTH[key]

  return (
    <header className="topbar">
      <div className="search">
        <Icon name="search" className="search-icon" />
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
        {/* Interruptor global: "só o Claude" ou "Claude com RAGX". O estado é
            dito em texto (Ligado/Desligado), não só pela cor do trilho. */}
        <Tooltip text={claudeTitle(claude)}>
          {(tip) => (
            <SwitchButton
              checked={claude.enabled === true}
              className={`topbar-button claude-toggle${claude.enabled ? ' is-on' : ''}${claude.error ? ' has-error' : ''}`}
              aria-label="RAGX no Claude Code"
              aria-busy={claude.busy}
              disabled={claude.enabled === null || claude.busy}
              {...tip}
              onClick={claude.toggle}
            >
              <SwitchTrack />
              RAGX no Claude
              <span className="switch-state">
                {claude.error ? 'erro' : claude.enabled === null ? '…' : claude.enabled ? 'ligado' : 'desligado'}
              </span>
              {claude.changed && !claude.error && <span className="switch-hint">próxima sessão</span>}
            </SwitchButton>
          )}
        </Tooltip>
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
              Conexões
              {h.state && <span className="health-state">{h.state}</span>}
            </button>
          )}
        </Tooltip>
      </div>
    </header>
  )
}

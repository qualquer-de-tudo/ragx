import { useId } from 'react'
import type { ClaudeProfile, ProjectSnapshot } from '../../types/ragx-bridge'
import type { AutoSetupView } from '../../hooks/useAutoSetup'
import { claudeHooksRow, gitHooksRow, lastRunSummary } from '../../hookRows'
import { formatRelative } from '../../format'
import { useClock } from '../../hooks/useClock'
import { Switch } from '../ui/Switch'

/**
 * "Ajuste automático": o painel mantém sozinho os hooks que fazem o RAGX funcionar de ponta a ponta (o aviso de edição
 * e o lembrete do Claude Code, e os hooks de git de cada projeto). Mostra o estado de cada um, a última rodada e o
 * interruptor para desligar.
 */
export function AutoSetupCard({
  auto,
  profiles,
  projects,
}: {
  auto: AutoSetupView
  profiles: readonly ClaudeProfile[]
  projects: readonly ProjectSnapshot[]
}) {
  const headId = useId()
  const clock = useClock(60_000)
  const { state } = auto
  const enabled = state?.enabled !== false
  const rows = [claudeHooksRow(profiles), gitHooksRow(projects)]
  const problema = state?.claude.error ?? (state && state.git.failed.length > 0 ? `Não consegui enfileirar: ${state.git.failed.join(', ')}.` : null)

  return (
    <section className="card auto-card" aria-labelledby={headId}>
      <header className="auto-head">
        <div>
          <h2 className="card-title" id={headId}>
            Ajuste automático
          </h2>
          <p className="auto-lede">
            {enabled
              ? 'O painel instala sozinho os hooks que mantêm o índice em dia.'
              : 'Desligado. Os hooks ficam como estão e nada é instalado sem você pedir.'}
          </p>
        </div>
        <Switch checked={enabled} label="Ajuste automático dos hooks" disabled={state === null} onChange={auto.setEnabled} />
      </header>

      <ul className="auto-rows">
        {rows.map((r) => (
          <li key={r.title} className={`auto-row auto-${r.tone}`}>
            <span className="auto-dot" aria-hidden="true" />
            <div className="auto-row-body">
              <p className="auto-row-title">{r.title}</p>
              <p className="auto-row-text">{r.text}</p>
            </div>
            <span className="sr-only">{r.tone === 'ok' ? 'em dia' : r.tone === 'warn' ? 'pede atenção' : 'sem o que conferir'}</span>
          </li>
        ))}
      </ul>

      {problema !== null && (
        <p className="callout callout-error auto-callout" role="alert">
          {problema}
        </p>
      )}

      <footer className="auto-foot">
        <p className="auto-last" role="status">
          {state?.running
            ? 'Ajustando…'
            : state?.lastRunAt
              ? `Verificado ${formatRelative(state.lastRunAt, new Date(clock))}. ${lastRunSummary(state)}`
              : enabled
                ? 'Primeira verificação em instantes.'
                : ''}
        </p>
        <button type="button" className="btn btn-sm" onClick={auto.run} disabled={!enabled || state === null || state.running}>
          Ajustar agora
        </button>
      </footer>
    </section>
  )
}

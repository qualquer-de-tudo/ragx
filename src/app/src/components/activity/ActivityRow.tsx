import type { ActivityEvent } from '../../types/ragx-bridge'
import { whatLabel, whoLabel } from '../../activity'
import { formatNumber, formatPercent, formatTime } from '../../format'
import { Tooltip } from '../ui/Tooltip'

function tokensText(e: ActivityEvent): string | null {
  if (e.tokensDelivered === null) return null
  if (e.baselineTokens === null || e.baselineTokens <= 0) return `${formatNumber(e.tokensDelivered)} tokens`
  const saved = 1 - e.tokensDelivered / e.baselineTokens
  return `${formatNumber(e.tokensDelivered)} de ${formatNumber(e.baselineTokens)} tokens (${saved >= 0 ? '−' : '+'}${formatPercent(Math.abs(saved))})`
}

function msText(ms: number | null): string | null {
  if (ms === null) return null
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`
}

const KIND_LABEL: Record<ActivityEvent['kind'], string> = { mcp: 'MCP', cli: 'CLI', session: 'Sessão' }

/**
 * Uma linha do feed de atividade: hora, tipo, o quê e onde, quem e os detalhes. Usada pelo feed e pela sessão expandida
 * (RAGX-0188). `onOpen` ausente (sessão, que já está dentro do projeto) mostra o nome do projeto como texto.
 */
export function ActivityRow({
  event: e,
  fresh = false,
  onOpen,
}: {
  event: ActivityEvent
  fresh?: boolean
  onOpen?: (projectId: string) => void
}) {
  const detalhes = [
    tokensText(e),
    msText(e.ms),
    e.ok === false ? (e.errCode ? `falhou (${e.errCode})` : 'falhou') : null,
    e.respChars !== null ? `${formatNumber(e.respChars)} caracteres na resposta` : null,
  ].filter(Boolean)
  return (
    <li className={`activity-item${fresh ? ' activity-item-fresh' : ''}`}>
      <Tooltip text={new Date(e.ts).toLocaleString('pt-BR')} focusable>
        {(tip) => (
          <time className="activity-time mono" dateTime={e.ts} {...tip}>
            {formatTime(e.ts)}
          </time>
        )}
      </Tooltip>
      <span className={`activity-kind activity-kind-${e.kind}`}>{KIND_LABEL[e.kind]}</span>
      <span className="activity-main">
        <span className="activity-what mono">{whatLabel(e)}</span>
        <span className="dim"> em </span>
        {onOpen ? (
          <button type="button" className="link-button" onClick={() => onOpen(e.projectId)}>
            {e.projectName}
          </button>
        ) : (
          <span>{e.projectName}</span>
        )}
      </span>
      <span className="activity-who">{whoLabel(e)}</span>
      <span className={`activity-meta dim${e.ok === false ? ' is-critical' : ''}`}>{detalhes.join(' · ')}</span>
    </li>
  )
}

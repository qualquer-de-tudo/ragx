import type { JobKind, JobView } from '../../types/ragx-bridge'
import { activeJobFor, jobStateLabel } from '../../state'
import { enqueue } from '../../jobs'

/**
 * Botão que enfileira uma tarefa do projeto. Com tarefa do mesmo tipo já na
 * fila ou rodando, fica desabilitado e diz "Na fila" ou "Rodando"; o nome
 * acessível continua dizendo qual ação é ("Atualizar agora: na fila").
 */
export function JobButton({
  kind,
  label,
  projectId,
  jobs,
  primary = false,
  disabled = false,
}: {
  kind: JobKind
  label: string
  projectId: string
  jobs: readonly JobView[]
  primary?: boolean
  disabled?: boolean
}) {
  const active = activeJobFor(jobs, projectId, [kind])
  const busy = active ? jobStateLabel(active) : null
  return (
    <button
      type="button"
      className={primary ? 'btn btn-primary' : 'btn'}
      disabled={disabled || busy !== null}
      aria-label={busy ? `${label}: ${busy.toLowerCase()}` : undefined}
      onClick={() => void enqueue(kind, projectId)}
    >
      {busy ?? label}
    </button>
  )
}

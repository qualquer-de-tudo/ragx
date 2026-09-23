import { useId } from 'react'
import type { JobView, ProjectSnapshot } from '../../types/ragx-bridge'
import { activeJobFor, jobStateLabel, missingEmbeddings } from '../../state'
import { enqueue } from '../../jobs'
import { ConfirmButton } from './ConfirmButton'
import { JobButton } from './JobButton'

/** Manutenção do índice: atualizar, gerar embeddings e reindexar do zero. */
export function MaintenancePanel({ project, jobs }: { project: ProjectSnapshot; jobs: readonly JobView[] }) {
  const titleId = useId()
  const full = activeJobFor(jobs, project.id, ['reindex-full'])
  const fullBusy = full ? jobStateLabel(full) : null

  return (
    <section className="card detail-card" aria-labelledby={titleId}>
      <h2 className="card-title" id={titleId}>
        Manutenção
      </h2>
      <div className="action-row">
        <JobButton
          kind="update"
          label="Atualizar agora"
          projectId={project.id}
          jobs={jobs}
          primary
          disabled={!project.exists}
        />
        <JobButton
          kind="embed"
          label="Gerar embeddings faltantes"
          projectId={project.id}
          jobs={jobs}
          disabled={!project.exists || missingEmbeddings(project.counts) === 0}
        />
      </div>
      <div className="danger-row">
        <p className="hint">Descarta o cache e lê todos os arquivos de novo. Use quando algo parecer errado no índice.</p>
        <ConfirmButton
          label={fullBusy ?? 'Reindexar do zero'}
          confirmLabel="Confirmar reindexação"
          tone="critical"
          disabled={!project.exists || fullBusy !== null}
          ariaLabel={fullBusy ? `Reindexar do zero: ${fullBusy.toLowerCase()}` : undefined}
          onConfirm={() => void enqueue('reindex-full', project.id)}
        />
      </div>
    </section>
  )
}

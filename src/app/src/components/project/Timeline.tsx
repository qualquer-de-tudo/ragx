import { useId } from 'react'
import type { IndexRun } from '../../projectStatus'
import { formatNumber, formatRelative } from '../../format'

const MAX_RUNS = 10

/** Quem disparou a indexação (`index_runs.source`). */
const SOURCE_LABEL: Record<string, string> = {
  cli: 'Terminal',
  panel: 'Painel',
  watch: 'Watcher',
  sync: 'Sync',
  'mcp:refresh': 'Agente (refresh)',
  'mcp:index': 'Agente (reindex)',
  'hook:post-checkout': 'Troca de branch',
  'hook:post-commit': 'Commit',
  'hook:post-merge': 'Merge ou pull',
}

const MODE_LABEL: Record<string, string> = {
  incremental: 'incremental',
  full: 'completa',
  'embed-only': 'só embeddings',
}

function label(map: Record<string, string>, value: string | null): string {
  if (value === null) return 'sem dados'
  return Object.hasOwn(map, value) ? map[value] : value
}

function absolute(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

function outcome(run: IndexRun, isLatest: boolean, running: boolean): { text: string; tone: 'critical' | null } {
  if (run.error !== null) return { text: run.error, tone: 'critical' }
  if (run.finishedAt === null) {
    return { text: isLatest && running ? 'em andamento' : 'não terminou', tone: null }
  }
  if (run.indexed === null) return { text: 'sem dados', tone: null }
  if (run.indexed === 0) return { text: 'sem mudanças', tone: null }
  return { text: `${formatNumber(run.indexed)} arquivo(s) reindexado(s)`, tone: null }
}

/**
 * As últimas indexações do projeto: quando, quem disparou, em que branch e
 * commit, e o que mudou. É o que responde "o índice acompanha o que eu faço?".
 */
export function Timeline({
  runs,
  pending,
  running,
}: {
  /** `null`: ainda não há resposta de `ragx status` (carregando ou erro). */
  runs: IndexRun[] | null
  /** Texto no lugar da lista enquanto `runs` é `null`. */
  pending: string
  /** Há indexação rodando agora (do snapshot): o run sem fim mais novo é ela. */
  running: boolean
}) {
  const titleId = useId()
  const shown = runs?.slice(0, MAX_RUNS) ?? null

  return (
    <section className="card detail-card" aria-labelledby={titleId}>
      <h2 className="card-title" id={titleId}>
        Linha do tempo
      </h2>
      {shown === null ? (
        <p className="dim">{pending}</p>
      ) : shown.length === 0 ? (
        <p className="dim">Nenhuma indexação registrada ainda.</p>
      ) : (
        <ol className="timeline">
          {shown.map((run, i) => {
            const at = run.finishedAt ?? run.startedAt
            const result = outcome(run, i === 0, running)
            return (
              <li key={run.key} className="timeline-item">
                <span className="timeline-dot" aria-hidden="true" />
                <div className="timeline-body">
                  <p className="timeline-head">
                    {at ? (
                      <time className="timeline-when" dateTime={at} title={absolute(at)}>
                        {formatRelative(at)}
                      </time>
                    ) : (
                      <span className="timeline-when">sem dados</span>
                    )}
                    <span className="timeline-source">{label(SOURCE_LABEL, run.source)}</span>
                    <span className="timeline-mode">{label(MODE_LABEL, run.mode)}</span>
                  </p>
                  <p className="timeline-meta">
                    {run.branch !== null && <span className="mono">{run.branch}</span>}
                    {run.commit !== null && <span className="mono timeline-commit">{run.commit.slice(0, 7)}</span>}
                    <span className={result.tone === 'critical' ? 'is-critical' : undefined}>{result.text}</span>
                  </p>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

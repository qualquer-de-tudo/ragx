import { useId, useState } from 'react'
import { parseRunsPage, type IndexRun } from '../../projectStatus'
import { formatNumber, formatRelative } from '../../format'

/** Tamanho da página: o `ragx status` traz as 10 primeiras, o `ragx runs` o resto. */
const PAGE = 10

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
  projectId,
  runs,
  pending,
  running,
}: {
  /** Para pedir as páginas seguintes (`ragx runs`). */
  projectId: string
  /** `null`: ainda não há resposta de `ragx status` (carregando ou erro). */
  runs: IndexRun[] | null
  /** Texto no lugar da lista enquanto `runs` é `null`. */
  pending: string
  /** Há indexação rodando agora (do snapshot): o run sem fim mais novo é ela. */
  running: boolean
}) {
  const titleId = useId()
  // As páginas extras pertencem às primeiras que vieram do status: quando elas
  // mudam (indexação nova), a lista volta para a primeira página.
  const firstKey = runs?.[0]?.key ?? null
  const [more, setMore] = useState<{ firstKey: string | null; runs: IndexRun[]; total: number | null }>({
    firstKey,
    runs: [],
    total: null,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const extra = more.firstKey === firstKey ? more : { firstKey, runs: [], total: null }

  const head = runs?.slice(0, PAGE) ?? null
  const seen = new Set(head?.map((r) => r.key))
  const shown = head === null ? null : [...head, ...extra.runs.filter((r) => !seen.has(r.key))]
  const hasMore =
    shown !== null && (extra.total !== null ? shown.length < extra.total : head !== null && head.length >= PAGE)

  async function loadMore() {
    if (shown === null) return
    setLoading(true)
    setError(null)
    try {
      const page = parseRunsPage(await window.ragx.getIndexRuns(projectId, shown.length), shown.length)
      if (page === null) throw new Error('resposta inesperada do ragx runs')
      setMore({ firstKey, runs: [...extra.runs, ...page.runs], total: page.total })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

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
      {error && <p className="callout callout-error">Não foi possível carregar mais: {error}</p>}
      {hasMore && (
        <div className="timeline-more">
          <button type="button" className="btn" onClick={() => void loadMore()} disabled={loading}>
            {loading ? 'Carregando…' : 'Carregar mais'}
          </button>
          {extra.total !== null && shown !== null && (
            <span className="hint">
              {formatNumber(shown.length)} de {formatNumber(extra.total)}
            </span>
          )}
        </div>
      )}
    </section>
  )
}

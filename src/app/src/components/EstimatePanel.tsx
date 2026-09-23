import { useState } from 'react'
import type { TrialResult } from '../types/ragx-bridge'
import { readCache, writeTrial, type Cached } from '../onDemandCache'
import { formatNumber, formatPercent, formatTime } from '../format'

interface Props {
  projectId: string
  projectPath: string | null
}

type State = Cached<TrialResult> | 'loading' | { error: string } | null

export function EstimatePanel({ projectId, projectPath }: Props) {
  const [state, setState] = useState<State>(() => readCache(projectId).trial ?? null)

  async function run() {
    if (!projectPath) return
    setState('loading')
    try {
      setState(writeTrial(projectId, await window.ragx.runTrial(projectPath)))
    } catch (err) {
      setState({ error: err instanceof Error ? err.message : String(err) })
    }
  }

  const loading = state === 'loading'
  const done = state !== null && state !== 'loading' && 'result' in state ? state : null
  const failed = state !== null && state !== 'loading' && 'error' in state ? state.error : null

  return (
    <section className="panel" aria-labelledby="estimate-title">
      <div className="panel-head">
        <h2 id="estimate-title">Economia estimada</h2>
        <span className="tag">estimativa</span>
      </div>
      <p className="panel-lede">
        Compara o contexto que o RAGX monta com a leitura dos arquivos inteiros, usando as consultas
        de avaliação do projeto. Não mede o uso real dos agentes.
      </p>

      {done && <TrialFigures result={done.result} at={done.at} />}
      {failed && <p className="callout callout-error">Não foi possível calcular agora: {failed}</p>}

      <div className="panel-actions">
        <button type="button" className="btn" onClick={run} disabled={loading || !projectPath}>
          {loading ? 'Calculando…' : done ? 'Recalcular estimativa' : 'Ver economia estimada'}
        </button>
        {!projectPath && <p className="hint">Disponível apenas para projetos clonados localmente.</p>}
      </div>
    </section>
  )
}

function TrialFigures({ result, at }: { result: TrialResult; at: string }) {
  const { saved_ratio, baseline_tokens, ragx_tokens, source_coverage } = result.totals
  const saves = saved_ratio >= 0
  return (
    <div className="trial">
      <p className="trial-figure">
        <span className="trial-value">{formatPercent(Math.abs(saved_ratio))}</span>
        <span className="trial-unit">{saves ? 'menos tokens' : 'mais tokens'}</span>
      </p>
      <dl className="pairs">
        <div>
          <dt>Lendo os arquivos</dt>
          <dd>{formatNumber(baseline_tokens)}</dd>
        </div>
        <div>
          <dt>Com o contexto do RAGX</dt>
          <dd>{formatNumber(ragx_tokens)}</dd>
        </div>
        <div>
          <dt>Fontes certas encontradas</dt>
          <dd>{formatPercent(source_coverage)}</dd>
        </div>
      </dl>
      <p className="stamp">Calculada às {formatTime(at)}</p>
    </div>
  )
}

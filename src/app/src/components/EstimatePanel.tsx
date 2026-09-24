import { useState } from 'react'
import type { TrialResult } from '../types/ragx-bridge'
import { readCache, writeTrial, type Cached } from '../onDemandCache'
import { formatNumber, formatPercent, formatTime } from '../format'
import { Badge } from './shell/Badge'

interface Props {
  projectId: string
  projectPath: string | null
}

type State = Cached<TrialResult> | 'loading' | { error: string } | null

/**
 * Simulação (`ragx trial`): o contexto que o RAGX monta contra a leitura dos
 * arquivos inteiros, com as consultas de avaliação do projeto ou, sem elas,
 * consultas geradas do próprio índice. Vive dentro do card "Economia de
 * tokens", abaixo do uso real.
 */
export function TrialEstimate({ projectId, projectPath }: Props) {
  const [state, setState] = useState<State>(() => readCache(projectId).trial ?? null)

  async function run() {
    if (!projectPath) return
    setState('loading')
    try {
      setState(writeTrial(projectId, await window.ragx.runTrial(projectId)))
    } catch (err) {
      setState({ error: err instanceof Error ? err.message : String(err) })
    }
  }

  const loading = state === 'loading'
  const done = state !== null && state !== 'loading' && 'result' in state ? state : null
  const failed = state !== null && state !== 'loading' && 'error' in state ? state.error : null

  return (
    <div className="trial-block">
      <div className="card-head">
        <h3 className="subhead">Simulação</h3>
        <Badge tone="muted">estimativa</Badge>
      </div>
      <p className="dim panel-lede">
        Roda consultas de exemplo e compara o contexto do RAGX com a leitura dos arquivos inteiros. Não mede o uso real.
      </p>

      {done && <TrialFigures result={done.result} at={done.at} />}
      {failed && <p className="callout callout-error">Não foi possível calcular agora: {failed}</p>}

      <div className="action-row">
        <button type="button" className="btn" onClick={run} disabled={loading || !projectPath}>
          {loading ? 'Calculando… (pode levar um minuto)' : done ? 'Simular de novo' : 'Simular economia'}
        </button>
        {!projectPath && <p className="hint">Disponível apenas para projetos clonados localmente.</p>}
      </div>
    </div>
  )
}

function TrialFigures({ result, at }: { result: TrialResult; at: string }) {
  const { saved_ratio, baseline_tokens, ragx_tokens, source_coverage } = result.totals
  const saves = saved_ratio >= 0
  return (
    <div className="trial">
      <p className="trial-figure trial-figure-sm">
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
      <p className="hint">
        {result.auto_generated
          ? `${result.cases ?? 'Algumas'} consultas geradas dos arquivos do projeto (ele não tem tests/eval/queries.yaml). `
          : ''}
        Calculada às {formatTime(at)}
      </p>
    </div>
  )
}

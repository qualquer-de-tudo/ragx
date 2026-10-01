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
        Roda consultas de exemplo e compara o contexto do RAGX com a leitura de arquivos inteiros, de duas maneiras. É uma estimativa: não mede o uso real.
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
  const t = result.totals
  // A manchete é a economia CONSERVADORA (contra o menor dos dois baselines) quando o
  // CLI a traz; o `ragx trial` antigo só tem o baseline "arquivos certos, inteiros".
  const ratio = t.saved_ratio_conservative ?? t.saved_ratio
  const conservadora = t.saved_ratio_conservative !== undefined
  const saves = ratio >= 0
  const oraculo = t.baseline_oracle_tokens ?? t.baseline_tokens
  return (
    <div className="trial">
      <p className="trial-figure trial-figure-sm">
        <span className="trial-value">{formatPercent(Math.abs(ratio))}</span>
        <span className="trial-unit">{saves ? 'menos tokens' : 'mais tokens'}</span>
      </p>
      <p className="hint">{conservadora ? 'Economia estimada, contra o menor dos dois baselines.' : 'Economia estimada.'}</p>
      <dl className="pairs">
        <div>
          <dt>Arquivos certos, lidos inteiros</dt>
          <dd>{formatNumber(oraculo)}</dd>
        </div>
        {t.baseline_grep_tokens !== undefined && (
          <div>
            <dt>Busca por palavra-chave e leitura (simulada)</dt>
            <dd>{formatNumber(t.baseline_grep_tokens)}</dd>
          </div>
        )}
        <div>
          <dt>Com o contexto do RAGX</dt>
          <dd>{formatNumber(t.ragx_tokens)}</dd>
        </div>
        <div>
          <dt>Fontes certas encontradas</dt>
          <dd>{formatPercent(t.source_coverage)}</dd>
        </div>
      </dl>
      <p className="hint">
        {result.auto_generated
          ? `${result.cases ?? 'Algumas'} consultas geradas dos arquivos do projeto (ele não tem tests/eval/queries.yaml). `
          : ''}
        São dois proxies, não uma sessão real de agente. Calculada às {formatTime(at)}
      </p>
    </div>
  )
}

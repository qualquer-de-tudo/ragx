import { useId } from 'react'
import type { UsageBlock, UsageMetrics, UsageReport } from '../../types/ragx-bridge'
import { formatCompact, formatNumber, formatPercent, formatRelative } from '../../format'
import type { UsageState } from '../../hooks/useUsage'
import { Badge } from '../shell/Badge'
import { Stat } from '../shell/Card'
import { EmptyState } from '../ui/EmptyState'

/** Linhas da tabela: rótulo, métrica e se é tamanho de resultado (caracteres, mostrados em ≈ tokens). */
const ROWS: ReadonlyArray<[string, keyof UsageMetrics, boolean]> = [
  ['Turnos (respostas do modelo)', 'turns', false],
  ['Tokens no total', 'totalTokens', false],
  ['Lidos do cache', 'cacheReadTokens', false],
  ['Gravados no cache', 'cacheCreationTokens', false],
  ['Entrada sem cache', 'inputTokens', false],
  ['Saída', 'outputTokens', false],
  ['Buscas', 'searchCalls', false],
  ['Leituras', 'readCalls', false],
  ['Chamadas ao RAGX', 'ragxCalls', false],
  ['Resultado de busca (≈ tokens)', 'searchResultChars', true],
  ['Resultado de leitura (≈ tokens)', 'readResultChars', true],
]

function cell(m: UsageMetrics | null, key: keyof UsageMetrics, chars: boolean, perToken: number): string {
  if (m === null) return 'sem sessões'
  const v = chars ? m[key] / perToken : m[key]
  return formatCompact(Math.round(v))
}

/** "4 de 64 sessões chamaram o RAGX (6%)" e, quando houve lembrete, quantas o chamaram depois dele. */
function adoptionText(b: UsageBlock): string {
  const a = b.adoption
  const base = `${formatNumber(a.withRagx)} de ${formatNumber(a.sessions)} sessões chamaram o RAGX (${formatPercent(a.withRagx / a.sessions)})`
  if (a.reminded === 0) return `${base}.`
  return `${base}. O lembrete apareceu em ${formatNumber(a.reminded)}; ${formatNumber(a.ragxAfterReminder)} chamaram o RAGX depois dele.`
}

/** O conteúdo do consumo real de um bloco (um projeto ou todos): números, tabela com e sem RAGX e adoção. */
export function UsageFigures({ block: b, report }: { block: UsageBlock; report: UsageReport }) {
  const tableId = useId()
  const all = b.all.median
  const perToken = report.charsPerToken || 4
  const cacheShare = all && all.totalTokens > 0 ? all.cacheReadTokens / all.totalTokens : null
  return (
    <>
      <div className="stats stats-4">
        <Stat
          label="Sessões"
          value={formatNumber(b.sessions)}
          note={`${formatNumber(b.withRagx.sessions)} com RAGX · ${formatNumber(b.withoutRagx.sessions)} sem`}
        />
        <Stat
          label="Tokens por sessão"
          value={all ? formatCompact(Math.round(all.totalTokens)) : 'sem dados'}
          note={cacheShare === null ? 'mediana' : `mediana · ${formatPercent(cacheShare)} lidos do cache`}
        />
        <Stat label="Turnos por sessão" value={all ? formatNumber(Math.round(all.turns)) : 'sem dados'} note="mediana" />
        <Stat
          label="Buscas e leituras"
          value={all ? `${formatNumber(Math.round(all.searchCalls))} / ${formatNumber(Math.round(all.readCalls))}` : 'sem dados'}
          note="mediana por sessão"
        />
      </div>
      <table className="bench-table usage-table" aria-labelledby={tableId}>
        <caption id={tableId} className="usage-caption">
          Mediana por sessão, com e sem RAGX
        </caption>
        <thead>
          <tr>
            <th scope="col">Medida</th>
            <th scope="col">Com RAGX ({formatNumber(b.withRagx.sessions)})</th>
            <th scope="col">Sem RAGX ({formatNumber(b.withoutRagx.sessions)})</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([label, key, chars]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              <td>{cell(b.withRagx.median, key, chars, perToken)}</td>
              <td>{cell(b.withoutRagx.median, key, chars, perToken)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="adoption-line" role="status">
        {adoptionText(b)}
      </p>
    </>
  )
}

/** O aviso que acompanha todo número de consumo real: é observação, não experimento. */
export function UsageNote({ report }: { report: UsageReport }) {
  return (
    <p className="hint">
      Observação, não experimento: sessões com e sem RAGX são tarefas diferentes, então a diferença não prova que o
      RAGX a causou. Lido das sessões do Claude Code (todos os perfis) iniciadas nos últimos {report.days} dias: só
      números, nunca o texto, os comandos ou os arquivos. O resultado de busca e de leitura é estimado em{' '}
      {report.charsPerToken} caracteres por token; leitura de imagem fica de fora.
    </p>
  )
}

/** Cabeçalho do card: título, selo de observação e "Atualizar". */
export function UsageHead({
  titleId,
  title,
  state,
}: {
  titleId: string
  title: string
  state: UsageState
}) {
  const generated = state.report?.generatedAt ?? null
  return (
    <>
      <div className="card-head">
        <h2 className="card-title" id={titleId}>
          {title}
        </h2>
        <Badge tone="muted">observação</Badge>
        <span className="hint usage-when">
          {state.loading ? 'Lendo as sessões…' : generated ? `lido ${formatRelative(generated)}` : null}{' '}
          <button type="button" className="btn btn-quiet btn-sm" onClick={state.refresh} disabled={state.loading}>
            Atualizar
          </button>
        </span>
      </div>
      {state.error && state.report && <p className="hint">Não foi possível atualizar agora: {state.error}</p>}
    </>
  )
}

/**
 * "Consumo real" na Atividade (RAGX-0205): todas as sessões em projetos do RAGX e a adoção por projeto. `null` sem
 * relatório ou sem sessão nenhuma: aí a Atividade mostra a adoção pelo log do servidor, como antes.
 */
export function ActivityRealUsage({ state }: { state: UsageState }) {
  const titleId = useId()
  const { report } = state
  if (report === null || report.overall.sessions === 0) return null
  return (
    <section className="card detail-card real-usage" aria-labelledby={titleId}>
      <UsageHead titleId={titleId} title="Consumo real nas sessões do Claude Code" state={state} />
      <UsageFigures block={report.overall} report={report} />
      {report.projects.length > 1 && (
        <ul className="adoption-projects" aria-label="Adoção por projeto">
          {report.projects.map((p) => (
            <li key={p.id ?? p.name}>
              {p.name}: {formatNumber(p.adoption.withRagx)} de {formatNumber(p.adoption.sessions)}
              {p.adoption.reminded > 0
                ? ` · depois do lembrete: ${formatNumber(p.adoption.ragxAfterReminder)} de ${formatNumber(p.adoption.reminded)}`
                : ''}
            </li>
          ))}
        </ul>
      )}
      <UsageNote report={report} />
    </section>
  )
}

/** "Consumo real" no detalhe do projeto (RAGX-0205): as sessões do Claude Code abertas na pasta dele ou numa worktree. */
export function ProjectRealUsage({ projectId, state }: { projectId: string; state: UsageState }) {
  const titleId = useId()
  const { report, error, loading } = state
  const block = report?.projects.find((p) => p.id === projectId) ?? null
  return (
    <section className="card detail-card real-usage" aria-labelledby={titleId}>
      <UsageHead titleId={titleId} title="Consumo real" state={state} />
      {report === null ? (
        error ? (
          <p className="callout callout-error">Não foi possível ler as sessões do Claude Code: {error}</p>
        ) : (
          <p className="dim">{loading ? 'Lendo as sessões do Claude Code. Na primeira vez pode levar um minuto.' : null}</p>
        )
      ) : block === null || block.sessions === 0 ? (
        <EmptyState className="dim">
          Nenhuma sessão do Claude Code neste projeto nos últimos {report.days} dias. Os números aparecem aqui quando
          alguém abrir o Claude Code na pasta dele ou numa worktree.
        </EmptyState>
      ) : (
        <UsageFigures block={block} report={report} />
      )}
      {report !== null && <UsageNote report={report} />}
    </section>
  )
}

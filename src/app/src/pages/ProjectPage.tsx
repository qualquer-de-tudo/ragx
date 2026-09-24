import { useEffect, useId, useMemo, useState, type ReactNode } from 'react'
import type { JobView, ProjectSnapshot } from '../types/ragx-bridge'
import type { TelemetrySummary } from '../../electron/data/types'
import {
  activeJobFor,
  busyProjectIds,
  deriveProjectState,
  jobStateLabel,
  missingEmbeddings,
  STATE_LABEL,
  STATE_TONE,
} from '../state'
import { formatNumber, formatPercent, formatRelative } from '../format'
import { parseProjectStatus, reasonText, UNKNOWN_FRESHNESS_TEXT, type ProjectStatus } from '../projectStatus'
import { enqueue } from '../jobs'
import { Badge } from '../components/shell/Badge'
import { BranchIcon } from '../components/project/ProjectCard'
import { ConfirmButton } from '../components/project/ConfirmButton'
import { JobButton } from '../components/project/JobButton'
import { MaintenancePanel } from '../components/project/MaintenancePanel'
import { Timeline } from '../components/project/Timeline'
import { TokenSavings } from '../components/project/TokenSavings'
import { SecurityPanel } from '../components/SecurityPanel'

type StatusView =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ok'; status: ProjectStatus }

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/**
 * Resposta de `ragx status --json` para o projeto. Pede de novo quando o
 * snapshot mostra que algo mudou (indexação nova, troca de branch ou commit,
 * embeddings gerados); enquanto a resposta nova não chega, fica a anterior.
 */
function useProjectStatus(project: ProjectSnapshot | null): StatusView {
  const [result, setResult] = useState<{ id: string; view: StatusView } | null>(null)
  const id = project?.id ?? null
  const canCheck = project !== null && project.exists && project.path !== null
  const changeKey = project
    ? [project.index?.finishedAt, project.git?.branch, project.git?.commit, project.counts?.pendingEmbeddings].join('|')
    : ''

  useEffect(() => {
    if (id === null || !canCheck) return
    let cancelled = false
    // `Promise.resolve().then` também transforma um throw síncrono em rejeição.
    Promise.resolve()
      .then(() => window.ragx.getProjectStatus(id))
      .then(
        (raw) => {
          if (cancelled) return
          const status = parseProjectStatus(raw)
          setResult({
            id,
            view: status
              ? { phase: 'ok', status }
              : { phase: 'error', message: 'resposta inesperada do ragx status' },
          })
        },
        (err: unknown) => {
          if (!cancelled) setResult({ id, view: { phase: 'error', message: errorMessage(err) } })
        },
      )
    return () => {
      cancelled = true
    }
  }, [id, canCheck, changeKey])

  if (project !== null && !canCheck) {
    return { phase: 'error', message: project.countsUnavailableReason ?? 'a pasta do projeto não existe mais' }
  }
  return result !== null && result.id === id ? result.view : { phase: 'loading' }
}

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" className="btn btn-quiet btn-icon back" aria-label="Voltar para Projetos" onClick={onBack}>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M15 5l-7 7 7 7" />
      </svg>
    </button>
  )
}

/** Seção com título `h2` que dá nome à região (leitor de tela e testes). */
function Section({ title, className, children }: { title: string; className?: string; children: ReactNode }) {
  const titleId = useId()
  return (
    <section className={`card detail-card${className ? ` ${className}` : ''}`} aria-labelledby={titleId}>
      <h2 className="card-title" id={titleId}>
        {title}
      </h2>
      {children}
    </section>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  )
}

function coverageText(counts: NonNullable<ProjectSnapshot['counts']>): string {
  if (counts.chunks === 0) return 'sem dados'
  // Arredonda para baixo: faltando um chunk, não mostra "100%".
  const ratio = counts.embeddings >= counts.chunks ? 1 : Math.floor((counts.embeddings / counts.chunks) * 100) / 100
  return formatPercent(ratio)
}

function IndexSection({ project, jobs }: { project: ProjectSnapshot; jobs: readonly JobView[] }) {
  const counts = project.counts
  const missing = missingEmbeddings(counts)
  return (
    <Section title="Índice">
      {counts === null ? (
        <p className="callout">{project.countsUnavailableReason ?? 'sem dados'}</p>
      ) : (
        <div className="stats stats-4">
          <Stat label="Documentos" value={formatNumber(counts.documents)} />
          <Stat label="Chunks" value={formatNumber(counts.chunks)} />
          <Stat label="Embeddings" value={formatNumber(counts.embeddings)} />
          <Stat label="Cobertura" value={coverageText(counts)} />
        </div>
      )}
      {missing > 0 && (
        <div className="callout callout-warning callout-action">
          <p>
            <span className="is-warning" aria-hidden="true">
              ▲{' '}
            </span>
            {formatNumber(missing)} chunks sem embedding: a busca semântica cai para palavra-chave nesses trechos.
          </p>
          <JobButton
            kind="embed"
            label="Gerar embeddings"
            projectId={project.id}
            jobs={jobs}
            primary
            disabled={!project.exists}
          />
        </div>
      )}
      {project.embeddingModel && <p className="hint">Modelo de embedding: {project.embeddingModel}</p>}
    </Section>
  )
}

function FreshnessSection({ project, view }: { project: ProjectSnapshot; view: StatusView }) {
  let body
  if (view.phase === 'loading') {
    body = (
      <p className="dim" role="status">
        Verificando…
      </p>
    )
  } else if (view.phase === 'error') {
    body = <p className="callout callout-error">Não foi possível verificar agora: {view.message}</p>
  } else {
    const { state, reasons } = view.status.freshness
    if (state === 'fresh') {
      body = (
        <p className="status-line is-good">
          <span aria-hidden="true">●</span> Em dia com o que está no disco
        </p>
      )
    } else if (state === 'stale') {
      body =
        reasons.length === 0 ? (
          <p className="status-line is-warning">
            <span aria-hidden="true">●</span> O índice está defasado.
          </p>
        ) : (
          <ul className="reasons">
            {reasons.map((r, i) => (
              <li key={`${r.kind}-${i}`}>{reasonText(r)}</li>
            ))}
          </ul>
        )
    } else {
      body = <p className="dim">{UNKNOWN_FRESHNESS_TEXT}</p>
    }
  }
  return (
    <Section title="Está em dia?">
      {body}
      <p className="hint">
        {project.index
          ? `Última indexação ${formatRelative(project.index.finishedAt)}`
          : 'Ainda não indexado com esta versão'}
      </p>
    </Section>
  )
}

function HooksSection({ project, jobs }: { project: ProjectSnapshot; jobs: readonly JobView[] }) {
  const titleId = useId()
  const hooksJob = activeJobFor(jobs, project.id, ['hooks-install', 'hooks-uninstall'])
  const installed = project.hooksInstalled === true
  const noGit = project.exists && project.git === null
  const text = !project.exists
    ? 'sem dados'
    : noGit
      ? 'Este projeto não está num repositório git.'
      : installed
        ? 'Instalados: o índice se atualiza ao trocar de branch, commitar e fazer merge.'
        : 'Não instalados.'

  return (
    <section className="card detail-card" aria-labelledby={titleId}>
      <div className="switch-head">
        <h2 className="card-title" id={titleId}>
          Hooks de git
        </h2>
        <div className="switch-wrap">
          {hooksJob && <span className="hint">{jobStateLabel(hooksJob)}</span>}
          <button
            type="button"
            role="switch"
            className="switch"
            aria-checked={installed}
            aria-labelledby={titleId}
            disabled={!project.exists || noGit || hooksJob !== null}
            onClick={() => void enqueue(installed ? 'hooks-uninstall' : 'hooks-install', project.id)}
          >
            <span className="switch-knob" aria-hidden="true" />
          </button>
        </div>
      </div>
      <p className="dim">{text}</p>
    </section>
  )
}

/** As três ações que regravam `knowledge/`, cada uma com o que faz e quando usar. */
const KNOWLEDGE_ACTIONS = [
  {
    kind: 'sync',
    label: 'Sincronizar knowledge',
    what: 'Faz tudo de uma vez: atualiza o índice, o grafo e o dicionário e regrava a pasta.',
    when: 'Antes de um commit ou PR, para quem clonar receber o conhecimento em dia.',
  },
  {
    kind: 'graph',
    label: 'Reconstruir grafo',
    what: 'Refaz o mapa de quem chama, importa e depende de quem.',
    when: 'Depois de mudanças grandes de estrutura: pastas movidas, módulos renomeados.',
  },
  {
    kind: 'dictionary',
    label: 'Gerar dicionário',
    what: 'Refaz o resumo do projeto que o agente lê primeiro: tecnologias, serviços, módulos.',
    when: 'Quando entrou uma tecnologia ou um serviço novo.',
  },
] as const

function KnowledgeSection({ project, jobs }: { project: ProjectSnapshot; jobs: readonly JobView[] }) {
  const off = !project.exists
  return (
    <Section title="Conhecimento no git" className="knowledge">
      <p className="dim">
        A pasta <span className="mono">knowledge/</span> guarda o grafo e o dicionário deste projeto dentro do
        repositório. Quem clona (outra pessoa, outra máquina, a CI) recebe esse conhecimento pronto, sem reindexar do
        zero. Os hooks de git atualizam o índice local; estas ações atualizam o que vai para o git.
      </p>
      <ul className="knowledge-actions">
        {KNOWLEDGE_ACTIONS.map((a) => (
          <li key={a.kind}>
            <div>
              <p className="knowledge-what">{a.what}</p>
              <p className="hint">{a.when}</p>
            </div>
            <JobButton kind={a.kind} label={a.label} projectId={project.id} jobs={jobs} disabled={off} />
          </li>
        ))}
      </ul>
      <p className="callout callout-warning">
        Estas ações alteram arquivos versionados em knowledge/. Revise o diff antes de commitar.
      </p>
    </Section>
  )
}

function UsageSection({ telemetry }: { telemetry: TelemetrySummary }) {
  if (telemetry.totalCalls === 0) {
    return (
      <Section title="Uso pelos agentes nas últimas 24 h">
        <p className="dim">
          Nenhuma chamada nas últimas 24 h. Elas aparecem aqui assim que um agente usar o servidor MCP do RAGX neste
          projeto.
        </p>
      </Section>
    )
  }
  const tools = [...telemetry.callsByTool].sort((a, b) => b.count - a.count)
  const top = tools[0]?.count ?? 1
  return (
    <Section title="Uso pelos agentes nas últimas 24 h">
      <div className="stats stats-2">
        <Stat label="Chamadas MCP" value={formatNumber(telemetry.totalCalls)} />
        <Stat
          label="Tokens entregues"
          value={formatNumber(telemetry.tokensDelivered)}
          note="Medido nas respostas do build_context"
        />
      </div>
      <ul className="bars" aria-label="Chamadas por ferramenta">
        {tools.map((t) => (
          <li
            key={t.tool}
            title={`${t.tool}: ${formatNumber(t.count)} chamadas (${formatPercent(t.count / telemetry.totalCalls)})`}
          >
            <span className="bar-label">{t.tool}</span>
            <span className="bar-track" aria-hidden="true">
              <span className="bar-fill" style={{ width: `${Math.max(1.5, (t.count / top) * 100)}%` }} />
            </span>
            <span className="bar-value">{formatNumber(t.count)}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function RemoveFromHub({
  project,
  jobs,
  onBack,
}: {
  project: ProjectSnapshot
  jobs: readonly JobView[]
  onBack: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const active = activeJobFor(jobs, project.id, ['remove-from-hub'])
  const busy = active ? jobStateLabel(active) : null

  const remove = async () => {
    setError(null)
    try {
      await window.ragx.enqueueJob({ kind: 'remove-from-hub', projectId: project.id })
      onBack()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <footer className="detail-foot">
      <div className="danger-row">
        <p className="hint">Tira o projeto do painel. Nada é apagado no disco.</p>
        <ConfirmButton
          label={busy ?? 'Remover do hub'}
          confirmLabel="Confirmar remoção"
          tone="critical"
          disabled={busy !== null}
          ariaLabel={busy ? `Remover do hub: ${busy.toLowerCase()}` : undefined}
          onConfirm={() => void remove()}
        />
      </div>
      {error && <p className="callout callout-error">Não foi possível remover agora: {error}</p>}
    </footer>
  )
}

function branchText(git: ProjectSnapshot['git']): string {
  if (git === null) return 'Sem git'
  return git.branch ?? `HEAD destacado em ${git.commit.slice(0, 7)}`
}

/** Detalhe de um projeto: está em dia?, histórico de indexação e ações. */
export function ProjectPage({
  project,
  jobs,
  onBack,
}: {
  project: ProjectSnapshot | null
  jobs: readonly JobView[]
  onBack: () => void
}) {
  const status = useProjectStatus(project)
  const state = useMemo(
    () => (project ? deriveProjectState(project, busyProjectIds(jobs)) : null),
    [project, jobs],
  )

  if (project === null || state === null) {
    return (
      <section className="page">
        <BackButton onBack={onBack} />
        <header className="page-head">
          <h1 className="page-title">Projeto não encontrado</h1>
        </header>
        <p className="dim">Ele pode ter sido removido do hub.</p>
      </section>
    )
  }

  return (
    <section className="page detail">
      <BackButton onBack={onBack} />
      <header className="detail-head">
        <div className="detail-title-row">
          <h1 className="page-title">{project.name}</h1>
          <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
        </div>
        <p className="mono dim">{project.path ?? 'sem dados'}</p>
        <p className="detail-branch">
          <BranchIcon />
          <span className="project-card-branch">{branchText(project.git)}</span>
        </p>
      </header>

      <div className="detail-grid detail-grid-top">
        <IndexSection project={project} jobs={jobs} />
        <FreshnessSection project={project} view={status} />
      </div>

      <TokenSavings projectId={project.id} projectPath={project.path} savings={project.telemetry.savings} />

      <div className="detail-grid detail-grid-main">
        <Timeline
          key={project.id}
          projectId={project.id}
          runs={status.phase === 'ok' ? status.status.runs : null}
          pending={status.phase === 'loading' ? 'Verificando…' : 'sem dados'}
          running={project.running !== null}
        />
        <div className="detail-stack">
          <MaintenancePanel project={project} jobs={jobs} />
          <HooksSection project={project} jobs={jobs} />
        </div>
      </div>

      <div className="detail-grid detail-grid-2">
        <UsageSection telemetry={project.telemetry} />
        <SecurityPanel projectId={project.id} projectPath={project.path} />
      </div>

      <KnowledgeSection project={project} jobs={jobs} />

      <RemoveFromHub project={project} jobs={jobs} onBack={onBack} />
    </section>
  )
}

import { useEffect, useId, useMemo, useState } from 'react'
import type { ActivityEvent, JobView, ProjectSnapshot } from '../types/ragx-bridge'
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
import { formatNumber, formatPercent } from '../format'
import { parseProjectStatus, reasonText, UNKNOWN_FRESHNESS_TEXT, type StatusView } from '../projectStatus'
import { enqueue } from '../jobs'
import { useAdoption } from '../hooks/useAdoption'
import { Badge } from '../components/shell/Badge'
import { Section, Stat } from '../components/shell/Card'
import { LivePill } from '../components/shell/LivePill'
import { ConfirmButton } from '../components/project/ConfirmButton'
import { JobButton } from '../components/project/JobButton'
import { MaintenancePanel } from '../components/project/MaintenancePanel'
import { ContextPreview } from '../components/project/ContextPreview'
import { ProjectGlance } from '../components/project/ProjectGlance'
import { Timeline } from '../components/project/Timeline'
import { TokenSavings } from '../components/project/TokenSavings'
import { SecurityPanel } from '../components/SecurityPanel'
import { RelativeTime } from '../components/shell/RelativeTime'
import { Icon } from '../components/ui/Icon'
import { IconButton } from '../components/ui/IconButton'
import { Switch } from '../components/ui/Switch'
import { SkeletonRegion, SkeletonText } from '../components/ui/Skeleton'
import { Tooltip } from '../components/ui/Tooltip'
import { TabPanel, Tabs, type TabItem } from '../components/shell/Tabs'
import { lastProjectTab, rememberProjectTab, type ProjectTab } from '../projectTab'

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

// So o mount busca a adocao na pagina do projeto (nao ha feed aqui para disparar de novo).
const NO_EVENTS: ActivityEvent[] = []

function BackButton({ onBack }: { onBack: () => void }) {
  return <IconButton label="Voltar para Projetos" icon="back" className="back" onClick={onBack} />
}

/** Seção com título `h2` que dá nome à região (leitor de tela e testes). */
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
      <SkeletonRegion label="Verificando…">
        <SkeletonText lines={2} />
      </SkeletonRegion>
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
        {project.index ? (
          <>
            Última indexação <RelativeTime iso={project.index.finishedAt} />
          </>
        ) : (
          'Ainda não indexado com esta versão'
        )}
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
          <Switch
            checked={installed}
            labelledBy={titleId}
            disabled={!project.exists || noGit || hooksJob !== null}
            onChange={() => void enqueue(installed ? 'hooks-uninstall' : 'hooks-install', project.id)}
          />
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

function UsageSection({ telemetry, adoption }: { telemetry: TelemetrySummary; adoption: { withCalls: number; sessions: number } | null }) {
  const adoptionText =
    adoption && adoption.sessions > 0 ? (
      <p className="hint">
        Sessões que chamaram o RAGX: {formatNumber(adoption.withCalls)} de {formatNumber(adoption.sessions)}
      </p>
    ) : null
  if (telemetry.totalCalls === 0) {
    return (
      <Section title="Uso pelos agentes nas últimas 24 h">
        <p className="dim">
          Nenhuma chamada nas últimas 24 h. Elas aparecem aqui assim que um agente usar o servidor MCP do RAGX neste
          projeto.
        </p>
        {adoptionText}
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
      {adoptionText}
      <ul className="bars" aria-label="Chamadas por ferramenta">
        {tools.map((t) => (
          <Tooltip
            key={t.tool}
            text={`${t.tool}: ${formatNumber(t.count)} chamadas (${formatPercent(t.count / telemetry.totalCalls)})`}
            focusable
          >
            {(tip) => (
              <li {...tip}>
                <span className="bar-label">{t.tool}</span>
                <span className="bar-track" aria-hidden="true">
                  <span className="bar-fill" style={{ width: `${Math.max(1.5, (t.count / top) * 100)}%` }} />
                </span>
                <span className="bar-value">{formatNumber(t.count)}</span>
              </li>
            )}
          </Tooltip>
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
  live = false,
  onBack,
}: {
  project: ProjectSnapshot | null
  jobs: readonly JobView[]
  /** Houve atividade no último minuto (tela de atividade). */
  live?: boolean
  onBack: () => void
}) {
  const status = useProjectStatus(project)
  const adoption = useAdoption(NO_EVENTS)
  const projectAdoption = adoption?.byProject.find((p) => p.projectId === project?.id) ?? null
  const state = useMemo(
    () => (project ? deriveProjectState(project, busyProjectIds(jobs)) : null),
    [project, jobs],
  )
  const [tab, chooseTab] = useRememberedTab()
  const tabsId = useId()

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
          {live && <LivePill />}
        </div>
        <p className="mono dim">{project.path ?? 'sem dados'}</p>
        <p className="detail-branch">
          <Icon name="branch" size={14} className="project-card-icon" />
          <span className="project-card-branch">{branchText(project.git)}</span>
        </p>
      </header>

      <ProjectGlance
        project={project}
        state={state}
        status={status}
        live={live}
        jobs={jobs}
        onSeeSavings={() => chooseTab('economia')}
      />

      <Tabs label="Detalhe do projeto" tabs={PROJECT_TABS} active={tab} onChange={chooseTab} idPrefix={tabsId} />

      <TabPanel id="geral" idPrefix={tabsId} active={tab === 'geral'}>
        <div className="detail-grid detail-grid-top">
          <FreshnessSection project={project} view={status} />
          <IndexSection project={project} jobs={jobs} />
        </div>
        <UsageSection telemetry={project.telemetry} adoption={projectAdoption} />
      </TabPanel>

      <TabPanel id="economia" idPrefix={tabsId} active={tab === 'economia'}>
        <TokenSavings projectId={project.id} projectPath={project.path} savings={project.telemetry.savings} />
        {project.exists && project.path !== null && <ContextPreview key={project.id} projectId={project.id} />}
      </TabPanel>

      <TabPanel id="historico" idPrefix={tabsId} active={tab === 'historico'}>
        <Timeline
          key={project.id}
          projectId={project.id}
          runs={status.phase === 'ok' ? status.status.runs : null}
          pending={status.phase === 'loading' ? 'Verificando…' : 'sem dados'}
          running={project.running !== null}
        />
      </TabPanel>

      <TabPanel id="manutencao" idPrefix={tabsId} active={tab === 'manutencao'}>
        <div className="detail-grid detail-grid-2">
          <MaintenancePanel project={project} jobs={jobs} />
          <HooksSection project={project} jobs={jobs} />
        </div>
        <SecurityPanel projectId={project.id} projectPath={project.path} />
        <KnowledgeSection project={project} jobs={jobs} />
        <RemoveFromHub project={project} jobs={jobs} onBack={onBack} />
      </TabPanel>
    </section>
  )
}

/**
 * Onze blocos numa página só era informação demais de uma vez. O que se olha
 * todo dia (índice, está em dia?, uso) fica na primeira aba; o que se usa de
 * vez em quando (economia, histórico, manutenção) fica a um clique.
 */
const PROJECT_TABS: readonly TabItem<ProjectTab>[] = [
  { id: 'geral', label: 'Visão geral' },
  { id: 'economia', label: 'Economia de tokens' },
  { id: 'historico', label: 'Histórico' },
  { id: 'manutencao', label: 'Manutenção' },
]

function useRememberedTab(): [ProjectTab, (tab: ProjectTab) => void] {
  const [tab, setTab] = useState<ProjectTab>(lastProjectTab)
  const choose = (next: ProjectTab) => {
    setTab(next)
    rememberProjectTab(next)
  }
  return [tab, choose]
}

/*
 * Marcadores provisórios das páginas (Task 7). Cada um é trocado pela página
 * de verdade nas Tasks 9 e 10 (Projetos já é a página real, Task 8); ficam
 * aqui só para a casca ser navegável.
 */
import type { ConnectionCheck, ProjectSnapshot } from '../types/ragx-bridge'
import { deriveProjectState, STATE_LABEL, STATE_TONE } from '../state'
import { Badge, type Tone } from '../components/shell/Badge'

export function ProjectPlaceholder({
  project,
  busyIds,
  onBack,
}: {
  project: ProjectSnapshot | null
  busyIds: ReadonlySet<string>
  onBack: () => void
}) {
  const state = project ? deriveProjectState(project, busyIds) : null
  return (
    <section className="page">
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
      <header className="page-head">
        <h1 className="page-title">{project?.name ?? 'Projeto não encontrado'}</h1>
        {state && <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>}
      </header>
      {project && <p className="mono dim">{project.path ?? 'sem dados'}</p>}
    </section>
  )
}

const CONNECTION_BADGE: Record<ConnectionCheck['state'], { tone: Tone; label: string }> = {
  ok: { tone: 'good', label: 'Conectado' },
  warn: { tone: 'warning', label: 'Atenção' },
  error: { tone: 'critical', label: 'Não conectado' },
}

export function ConnectionsPlaceholder({
  connections,
  checking,
  onRefresh,
}: {
  connections: ConnectionCheck[] | null
  checking: boolean
  onRefresh: () => void
}) {
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Conexões</h1>
          <p className="page-lede">O painel confere estas três peças a cada 30 segundos.</p>
        </div>
        <button type="button" className="btn" onClick={onRefresh} disabled={checking}>
          {checking ? 'Verificando…' : 'Verificar agora'}
        </button>
      </header>
      {connections === null ? (
        <p className="empty" role="status">
          Verificando as conexões…
        </p>
      ) : (
        <ul className="grid-3">
          {connections.map((c) => (
            <li key={c.id} className="card">
              <div className="card-head">
                <h2 className="card-title">{c.title}</h2>
                <Badge tone={CONNECTION_BADGE[c.state].tone}>{CONNECTION_BADGE[c.state].label}</Badge>
              </div>
              <p className="dim">{c.summary}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function HowPlaceholder({ onRestart }: { onRestart: () => void }) {
  return (
    <section className="page">
      <header className="page-head">
        <h1 className="page-title">Como funciona</h1>
      </header>
      <div className="card prose">
        <p>
          O RAGX lê seus projetos aqui mesmo, na sua máquina, e entrega ao Claude Code só o trecho que importa, pelo
          MCP.
        </p>
        <button type="button" className="btn" onClick={onRestart}>
          Refazer configuração
        </button>
      </div>
    </section>
  )
}

export function OnboardingPlaceholder({ onSkip }: { onSkip: () => void }) {
  return (
    <main className="onboarding">
      <div className="onboarding-card card">
        <h1 className="page-title">Configuração inicial</h1>
        <p className="dim">Confira as conexões e adicione seus projetos. Você pode fazer isso depois.</p>
        <button type="button" className="btn btn-primary" onClick={onSkip}>
          Pular configuração
        </button>
      </div>
    </main>
  )
}

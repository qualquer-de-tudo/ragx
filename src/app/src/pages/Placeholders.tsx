/*
 * Marcadores provisórios das páginas (Task 7). Cada um é trocado pela página
 * de verdade na Task 10 (Projetos e o detalhe do projeto já são páginas
 * reais, Tasks 8 e 9); ficam aqui só para a casca ser navegável.
 */
import type { ConnectionCheck } from '../types/ragx-bridge'
import { Badge, type Tone } from '../components/shell/Badge'

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

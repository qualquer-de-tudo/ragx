import { useId, useState, type ReactNode } from 'react'
import type { ConnectionCheck, JobView } from '../../types/ragx-bridge'
import type { ClaudeToggle } from '../../hooks/useClaudeIntegration'
import { useMcpIntegrations } from '../../hooks/useMcpIntegrations'
import { Tabs, TabPanel } from '../shell/Tabs'
import { Switch } from '../ui/Switch'
import { ConnectionGrid } from './ConnectionCard'
import { ClaudeProfiles } from './ClaudeProfiles'
import { AgentConnection } from './AgentConnection'

const TABS = [
  { id: 'environment', label: 'Ambiente' }, { id: 'claude', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' }, { id: 'gemini', label: 'Gemini' }, { id: 'others', label: 'Outros agentes' },
] as const
type ConnectionTab = typeof TABS[number]['id']

export function ConnectionsTabs({ connections, jobs, claude, claudeExtra, refreshKey = 0 }: {
  connections: ConnectionCheck[] | null
  jobs: readonly JobView[]
  claude?: ClaudeToggle
  claudeExtra?: ReactNode
  refreshKey?: number
}) {
  const [active, setActive] = useState<ConnectionTab>('environment')
  const prefix = useId()
  const integrations = useMcpIntegrations(refreshKey)
  return (
    <div className="connections-workspace">
      <Tabs label="Conexões por agente" tabs={TABS} active={active} onChange={setActive} idPrefix={prefix} />
      <TabPanel id="environment" idPrefix={prefix} active={active === 'environment'}>
        <p className="connections-intro">A base é a mesma para todos os agentes: CLI e geração de embeddings na sua máquina.</p>
        <ConnectionGrid connections={connections?.filter((c) => c.id !== 'claude') ?? null} jobs={jobs} pendingTitles={['RAGX CLI', 'Ollama']} />
      </TabPanel>
      <TabPanel id="claude" idPrefix={prefix} active={active === 'claude'}>
        <p className="connections-intro">Conecte o Claude Code e escolha em quais contas o RAGX fica ligado.</p>
        {claude && <section className="card agent-control agent-global">
          <div>
            <h2 className="card-title">RAGX no Claude Code</h2>
            <p className="dim">Liga ou desliga em todos os perfis. Você também pode escolher cada conta abaixo.</p>
            <p className="agent-status">{claude.enabled === null ? 'Verificando…' : claude.enabled ? 'Ligado em todos os perfis.' : claude.profiles.some((p) => p.enabled) ? 'Ligado em alguns perfis.' : 'Desligado.'}</p>
          </div>
          <Switch label="RAGX no Claude Code" checked={claude.enabled === true}
            disabled={claude.enabled === null || claude.busy || claude.profiles.length === 0} onChange={claude.toggle} />
          {(claude.busy || claude.error || claude.changed) && <p className="agent-status" role="status">
            {claude.busy ? 'Alterando…' : claude.error ?? 'Vale a partir da próxima sessão do Claude Code.'}
          </p>}
        </section>}
        <ConnectionGrid connections={connections?.filter((c) => c.id === 'claude') ?? null} jobs={jobs}
          pendingTitles={['Claude Code']} extra={() => claude ? <ClaudeProfiles claude={claude} /> : null} />
        {claudeExtra}
      </TabPanel>
      <div className="agents-refresh" hidden={active === 'environment' || active === 'claude'}>
        <p className="dim">Conecte os agentes que você usa. Cada um compartilha o mesmo índice local.</p>
        <button type="button" className="btn btn-sm" disabled={integrations.loading || integrations.busy !== null}
          onClick={() => void integrations.refresh()}>{integrations.loading ? 'Verificando agentes…' : 'Verificar agentes'}</button>
        {integrations.error && <p className="callout callout-error" role="alert">{integrations.error}</p>}
      </div>
      <TabPanel id="codex" idPrefix={prefix} active={active === 'codex'}>
        <AgentConnection id="codex" integrations={integrations} />
      </TabPanel>
      <TabPanel id="gemini" idPrefix={prefix} active={active === 'gemini'}>
        <AgentConnection id="gemini" integrations={integrations} />
      </TabPanel>
      <TabPanel id="others" idPrefix={prefix} active={active === 'others'}>
        <div className="stack">
          {(['cursor', 'windsurf', 'claude-desktop'] as const).map((id) => <AgentConnection key={id} id={id} integrations={integrations} />)}
          <p className="callout">Usa outro agente? Clientes com suporte a MCP local podem iniciar o servidor com <code>ragx mcp serve</code>.</p>
        </div>
      </TabPanel>
    </div>
  )
}

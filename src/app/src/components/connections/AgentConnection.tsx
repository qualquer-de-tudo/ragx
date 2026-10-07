import { useId } from 'react'
import type { McpClientId } from '../../types/ragx-bridge'
import type { useMcpIntegrations } from '../../hooks/useMcpIntegrations'
import { Badge } from '../shell/Badge'
import { Switch } from '../ui/Switch'

const AGENTS = [
  { id: 'codex', label: 'Codex', detail: 'Contexto do seu projeto nas ferramentas do Codex.', mark: 'Cx' },
  { id: 'gemini', label: 'Gemini CLI', detail: 'Busca e contexto local para suas sessões no Gemini CLI.', mark: 'G' },
  { id: 'cursor', label: 'Cursor', detail: 'Conhecimento do projeto junto do seu editor.', mark: 'Cu' },
  { id: 'windsurf', label: 'Windsurf', detail: 'Busca e contexto para o agente do Windsurf.', mark: 'W' },
  { id: 'claude-desktop', label: 'Claude Desktop', detail: 'Ferramentas do RAGX nas conversas do Claude Desktop.', mark: 'Cl' },
] as const

export function AgentConnection({ id, integrations }: {
  id: McpClientId
  integrations: ReturnType<typeof useMcpIntegrations>
}) {
  const titleId = useId()
  const agent = AGENTS.find((a) => a.id === id)!
  const client = integrations.clients.find((c) => c.id === id)
  const label = integrations.loading && !client ? 'Verificando…'
    : !client ? 'Sem informação' : client.enabled ? 'RAGX ligado' : client.installed ? 'RAGX desligado' : 'Não detectado'
  return (
    <article className="card agent-card" aria-labelledby={titleId}>
      <div className="agent-card-head">
        <span className="agent-mark" aria-hidden="true">{agent.mark}</span>
        <div className="agent-ident">
          <h2 className="card-title" id={titleId}>{agent.label}</h2>
          <p className="dim">{agent.detail}</p>
        </div>
        <Badge tone={client?.enabled ? 'good' : 'muted'}>{label}</Badge>
      </div>
      <div className="agent-control">
        <div>
          <h3>RAGX neste agente</h3>
          <p className="dim">Ao ligar, o agente recebe as ferramentas de busca e contexto. Vale para todos os projetos indexados.</p>
        </div>
        <Switch
          label={`RAGX no ${agent.label}`}
          checked={client?.enabled === true}
          disabled={!client || (!client.installed && !client.enabled) || integrations.loading || integrations.busy !== null}
          onChange={(enabled) => void integrations.setEnabled(id, enabled)}
        />
      </div>
      {client && <p className="agent-status" role="status">
        {integrations.busy === id ? 'Alterando conexão…'
          : integrations.changed.has(id) ? `Reabra o ${agent.label} para carregar a configuração nova.`
          : !client.installed ? `Abra o ${agent.label} ao menos uma vez nesta conta e clique em Verificar agentes.`
          : client.enabled ? 'Registrado na configuração. O agente decide quando consultar o RAGX.'
          : 'Pronto para conectar. Ligue o RAGX no controle acima.'}
      </p>}
      {client && <details className="agent-config">
        <summary>Local da configuração</summary>
        <p className="mono dim">{client.config}</p>
      </details>}
    </article>
  )
}

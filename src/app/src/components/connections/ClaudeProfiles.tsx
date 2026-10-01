import { useId } from 'react'
import type { ClaudeToggle } from '../../hooks/useClaudeIntegration'
import { ConfirmButton } from '../project/ConfirmButton'
import { Switch } from '../ui/Switch'
import { Tooltip } from '../ui/Tooltip'

/**
 * Os perfis do Claude Code, dentro da faixa do Claude em Conexões: uma linha
 * por conta (cada `CLAUDE_CONFIG_DIR`), com o próprio interruptor. O padrão e
 * os `~/.claude-*` são detectados; os outros, adicionados escolhendo a pasta,
 * já ligados. "Remover" desliga antes de tirar da lista.
 */
export function ClaudeProfiles({ claude }: { claude: ClaudeToggle }) {
  const { profiles, busy, error, changed } = claude
  const headId = useId()
  const ligados = profiles.filter((p) => p.enabled).length
  return (
    <section className="conn-sub" aria-labelledby={headId}>
      <div className="conn-sub-head">
        <div>
          <h3 className="conn-sub-title" id={headId}>
            Perfis (contas)
          </h3>
          <p className="dim conn-sub-lede">
            {profiles.length === 0
              ? claude.enabled === null
                ? 'Lendo os perfis…'
                : 'Nenhum perfil do Claude Code encontrado nesta máquina.'
              : `RAGX ligado em ${ligados} de ${profiles.length}. Cada conta (um CLAUDE_CONFIG_DIR) tem a sua configuração.`}
          </p>
        </div>
        <button type="button" className="btn btn-sm" onClick={claude.addProfile} disabled={busy}>
          Adicionar perfil
        </button>
      </div>

      {profiles.length > 0 && (
        <ul className="profile-list" aria-label="Perfis do Claude Code">
          {profiles.map((p) => (
            <li key={p.id} className="profile-item">
              <div className="profile-main">
                <p className="profile-name">
                  {p.name}
                  <span className="profile-origin">{p.added ? 'adicionado' : 'detectado'}</span>
                  {p.enabled && !p.hint && <span className="profile-warn">sem a dica de início de sessão</span>}
                </p>
                <Tooltip text={p.dir} focusable>
                  {(tip) => (
                    <p className="mono dim profile-dir" {...tip}>
                      {p.dir}
                    </p>
                  )}
                </Tooltip>
              </div>
              <div className="profile-actions">
                {p.added && (
                  <ConfirmButton
                    label="Remover"
                    confirmLabel="Tirar o RAGX e remover"
                    onConfirm={() => claude.removeProfile(p.id)}
                    disabled={busy}
                  />
                )}
                <Switch
                  checked={p.enabled}
                  label={`RAGX no perfil ${p.name}`}
                  disabled={busy}
                  onChange={(next) => claude.setProfile(p.id, next)}
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      {(busy || error || changed) && (
        <p className="conn-sub-status" role="status">
          {busy ? (
            'Alterando…'
          ) : error ? (
            <span className="is-critical">{error}</span>
          ) : (
            'Vale a partir da próxima sessão do Claude Code.'
          )}
        </p>
      )}
    </section>
  )
}

import type { ClaudeToggle } from '../../hooks/useClaudeIntegration'
import { Section } from '../shell/Card'
import { ConfirmButton } from '../project/ConfirmButton'

/**
 * Um item por conta do Claude Code na máquina (cada `CLAUDE_CONFIG_DIR`): o
 * padrão, os `~/.claude-*` detectados e as pastas adicionadas à mão. Cada um
 * tem o próprio interruptor; o do topo liga e desliga todos. Adicionar pede a
 * pasta e já liga o RAGX nela; remover desliga antes de tirar da lista.
 */
export function ClaudeProfilesCard({ claude }: { claude: ClaudeToggle }) {
  const { profiles, busy, error, changed } = claude
  return (
    <Section title="Perfis do Claude Code" className="claude-profiles">
      <p className="dim">
        Cada conta do Claude Code (um <code>CLAUDE_CONFIG_DIR</code>) tem a sua configuração. O RAGX precisa estar
        ligado em cada uma que você usa; a dica de início de sessão vai junto.
      </p>

      {profiles.length === 0 ? (
        <p className="dim">{claude.enabled === null ? 'Lendo os perfis…' : 'Nenhum perfil do Claude Code encontrado nesta máquina.'}</p>
      ) : (
        <ul className="profile-list" aria-label="Perfis do Claude Code">
          {profiles.map((p) => (
            <li key={p.id} className="profile-item">
              <div className="profile-main">
                <p className="profile-name">
                  {p.name}
                  <span className="profile-origin">{p.added ? 'adicionado' : 'detectado'}</span>
                </p>
                <p className="mono dim profile-dir">{p.dir}</p>
                {p.enabled && !p.hint && <p className="hint is-warning">Ligado sem a dica de início de sessão.</p>}
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
                <button
                  type="button"
                  role="switch"
                  className="switch"
                  aria-checked={p.enabled}
                  aria-label={`RAGX no perfil ${p.name}`}
                  disabled={busy}
                  onClick={() => claude.setProfile(p.id, !p.enabled)}
                >
                  <span className="switch-knob" aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="profile-footer">
        <button type="button" className="btn" onClick={claude.addProfile} disabled={busy}>
          Adicionar perfil
        </button>
        <p className="dim" role="status">
          {busy
            ? 'Alterando…'
            : error
              ? <span className="is-critical">{error}</span>
              : changed
                ? 'Vale a partir da próxima sessão do Claude Code.'
                : 'Use "Adicionar perfil" para uma conta fora de ~/.claude-*: escolha a pasta dela.'}
        </p>
      </div>
    </Section>
  )
}

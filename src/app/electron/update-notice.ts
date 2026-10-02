/**
 * Aviso de versão nova (1.0.1): quando o `electron-updater` acha uma versão diferente da que está rodando, o painel
 * avisa uma vez por versão, mesmo com a janela fechada na bandeja ou fora da vista. Quem decide AQUI é só a regra
 * ("já avisei desta versão?"); a notificação do sistema e a persistência entram por injeção.
 */
import type { UpdateState } from './updater'

export interface UpdateNoticeDeps {
  /** A última versão de que já se avisou (gravada nas configurações). */
  notified: () => string | undefined
  remember: (version: string) => void
  show: (version: string, current: string) => void
}

/** `true` quando a versão do estado é de fato diferente da atual, e há uma versão a mostrar. */
export function isNewVersion(state: UpdateState): boolean {
  return state.version !== null && state.version.length > 0 && state.version !== state.currentVersion
}

export function createUpdateNotice(deps: UpdateNoticeDeps): (state: UpdateState) => void {
  return (state) => {
    if (state.status !== 'available' && state.status !== 'downloaded') return
    if (!isNewVersion(state) || state.version === null) return
    if (deps.notified() === state.version) return
    // Grava antes de mostrar: uma falha ao exibir não pode virar um aviso por checagem.
    deps.remember(state.version)
    deps.show(state.version, state.currentVersion)
  }
}

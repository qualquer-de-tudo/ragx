/**
 * Atualização do painel com `electron-updater` contra o GitHub Releases (RAGX-0192).
 *
 * **Desligada por padrão** (`autoUpdate`): o `.exe` não é assinado (RAGX-0124 adiada), então o Windows pode alertar no
 * update e a integridade fica a cargo do hash do `latest.yml`. Desligada, ou fora do painel empacotado, NÃO faz nenhuma
 * chamada de rede. Nunca baixa nem instala sozinha: `autoDownload` e `autoInstallOnAppQuit` ficam falsos, e cada passo
 * é um pedido da pessoa. Este módulo não importa `electron` nem `electron-updater`: o `autoUpdater` entra por injeção
 * (testável com um falso).
 */

export type UpdateStatus = 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error'

export interface UpdateState {
  status: UpdateStatus
  /** Versão do painel em execução. */
  currentVersion: string
  /** Versão nova, quando há (`available`, `downloading`, `downloaded`). */
  version: string | null
  /** 0 a 100 enquanto baixa. */
  progress: number | null
  /** Mensagem em português quando `status === 'error'`. */
  error: string | null
}

/** O pedaço de `electron-updater` que o módulo usa. */
export interface UpdaterLike {
  autoDownload: boolean
  autoInstallOnAppQuit: boolean
  channel: string | null
  allowPrerelease: boolean
  checkForUpdates: () => Promise<unknown>
  downloadUpdate: () => Promise<unknown>
  quitAndInstall: () => void
  on: (event: string, listener: (...args: never[]) => void) => unknown
}

export interface UpdaterDeps {
  autoUpdater: UpdaterLike
  /** `app.isPackaged`: em desenvolvimento não há o que atualizar. */
  isPackaged: boolean
  version: string
  /** Lê a preferência na hora (a pessoa pode ligar ou desligar com o painel aberto). */
  enabled: () => boolean
  onState: (state: UpdateState) => void
}

export interface Updater {
  init: () => void
  getState: () => UpdateState
  check: () => Promise<UpdateState>
  download: () => Promise<UpdateState>
  install: () => void
}

/** Mensagem em português; nunca devolve o texto cru de um erro de rede com caminhos ou URLs internas. */
function friendly(err: unknown): string {
  const text = err instanceof Error ? err.message : String(err)
  if (/ENOTFOUND|ECONNREFUSED|ETIMEDOUT|ECONNRESET|net::|network|getaddrinfo/i.test(text)) {
    return 'Não foi possível falar com o servidor de atualizações. Confira a conexão e tente de novo.'
  }
  if (/sha512|checksum|hash/i.test(text)) return 'A atualização baixada não passou na verificação de integridade e foi descartada.'
  return 'Não foi possível verificar ou baixar a atualização agora.'
}

export function createUpdater(deps: UpdaterDeps): Updater {
  const { autoUpdater } = deps
  let state: UpdateState = { status: 'idle', currentVersion: deps.version, version: null, progress: null, error: null }

  const set = (patch: Partial<UpdateState>) => {
    state = { ...state, ...patch }
    deps.onState(state)
  }

  return {
    init() {
      autoUpdater.autoDownload = false
      autoUpdater.autoInstallOnAppQuit = false
      autoUpdater.channel = 'latest'
      // A release beta sai marcada como prerelease em `release.yml`: o painel beta precisa enxergá-la.
      autoUpdater.allowPrerelease = deps.version.includes('-beta')
      autoUpdater.on('checking-for-update', () => set({ status: 'checking', error: null }))
      autoUpdater.on('update-available', ((info: { version?: string }) =>
        set({ status: 'available', version: info?.version ?? null, progress: null })) as never)
      autoUpdater.on('update-not-available', () => set({ status: 'idle', version: null, progress: null }))
      autoUpdater.on('download-progress', ((p: { percent?: number }) =>
        set({ status: 'downloading', progress: Math.round(p?.percent ?? 0) })) as never)
      autoUpdater.on('update-downloaded', ((info: { version?: string }) =>
        set({ status: 'downloaded', version: info?.version ?? state.version, progress: 100 })) as never)
      autoUpdater.on('error', ((err: unknown) => {
        console.error('electron-updater falhou:', err)
        set({ status: 'error', error: friendly(err) })
      }) as never)
    },

    getState: () => state,

    async check() {
      // desligada ou em desenvolvimento: zero chamadas de rede
      if (!deps.isPackaged || !deps.enabled()) return state
      if (state.status === 'checking' || state.status === 'downloading') return state
      set({ status: 'checking', error: null })
      try {
        await autoUpdater.checkForUpdates()
      } catch (err) {
        console.error('checkForUpdates() falhou:', err)
        set({ status: 'error', error: friendly(err) })
      }
      return state
    },

    async download() {
      // só baixa o que a pessoa pediu, e só depois de uma verificação que achou versão nova
      if (state.status !== 'available' || !deps.isPackaged || !deps.enabled()) return state
      set({ status: 'downloading', progress: 0 })
      try {
        await autoUpdater.downloadUpdate()
      } catch (err) {
        console.error('downloadUpdate() falhou:', err)
        set({ status: 'error', error: friendly(err) })
      }
      return state
    },

    install() {
      if (state.status !== 'downloaded') throw new Error('pedido recusado: não há atualização baixada')
      autoUpdater.quitAndInstall()
    },
  }
}

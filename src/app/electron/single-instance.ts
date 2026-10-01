/**
 * Uma só instância do painel (RAGX-0171). Sem trava, abrir o painel de novo subia outra casca com os
 * mesmos pollers (e o dobro de processos filhos).
 *
 * Os modos sem janela do instalador NSIS (`--bootstrap` e `--uninstall-cli`) NÃO pegam a trava: o
 * instalador os chama com o painel possivelmente aberto. `RAGX_PANEL_ALLOW_MULTI=1` desliga a trava (dev,
 * medição).
 */

/** O que se usa do `app` do Electron. */
export interface AppLike {
  requestSingleInstanceLock: () => boolean
  quit: () => void
  on: (event: 'second-instance', listener: () => void) => unknown
}

export interface SingleInstanceOptions {
  /** Modo sem janela (`--bootstrap`, `--uninstall-cli`): nunca pega nem respeita a trava. */
  headless: boolean
  /** `RAGX_PANEL_ALLOW_MULTI=1`. */
  allowMulti: boolean
  /** Uma segunda instância tentou abrir: restaurar, mostrar e focar a janela existente. */
  onSecondInstance: () => void
}

/** `true` se esta instância pode seguir; `false` se é uma segunda e já mandou o app sair. */
export function acquireSingleInstance(app: AppLike, opts: SingleInstanceOptions): boolean {
  if (opts.headless || opts.allowMulti) return true
  if (!app.requestSingleInstanceLock()) {
    app.quit()
    return false
  }
  app.on('second-instance', opts.onSecondInstance)
  return true
}

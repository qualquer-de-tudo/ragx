/**
 * "O painel está sendo visto?" (RAGX-0171): janela visível e não minimizada, tela desbloqueada, computador
 * acordado. Só quando as quatro coisas valem o painel precisa dos pollers.
 */

/** O que se usa da janela (`BrowserWindow`), para o teste trocar por um `EventEmitter`. */
export interface WindowLike {
  isVisible: () => boolean
  isMinimized: () => boolean
  on: (event: string, listener: () => void) => unknown
  removeListener: (event: string, listener: () => void) => unknown
}

/** O que se usa do `powerMonitor` (só existe depois do `ready`). */
export interface PowerLike {
  on: (event: string, listener: () => void) => unknown
  removeListener: (event: string, listener: () => void) => unknown
}

const WINDOW_EVENTS = ['show', 'hide', 'minimize', 'restore']

/**
 * Liga `onChange(ativo)` aos eventos da janela (`show`, `hide`, `minimize`, `restore`) e do sistema
 * (`suspend`, `resume`, `lock-screen`, `unlock-screen`). Só avisa quando o valor MUDA. Devolve a função de
 * limpeza. Retomar (`resume`, `unlock-screen`, `restore`) só reativa quando TODAS as condições voltaram.
 */
export function watchWindowActivity(
  win: WindowLike,
  power: PowerLike | null,
  onChange: (active: boolean) => void,
): () => void {
  let locked = false
  let suspended = false
  let last: boolean | null = null

  const compute = (): boolean => win.isVisible() && !win.isMinimized() && !locked && !suspended

  const evaluate = (): void => {
    const active = compute()
    if (active === last) return
    last = active
    onChange(active)
  }

  const handlers: Array<[string, () => void]> = [
    ['suspend', () => { suspended = true; evaluate() }],
    ['resume', () => { suspended = false; evaluate() }],
    ['lock-screen', () => { locked = true; evaluate() }],
    ['unlock-screen', () => { locked = false; evaluate() }],
  ]

  for (const event of WINDOW_EVENTS) win.on(event, evaluate)
  if (power) for (const [event, fn] of handlers) power.on(event, fn)
  last = compute()

  return () => {
    for (const event of WINDOW_EVENTS) win.removeListener(event, evaluate)
    if (power) for (const [event, fn] of handlers) power.removeListener(event, fn)
  }
}

/**
 * Poller que pode ser pausado (RAGX-0171).
 *
 * Os três pollers do processo principal (snapshot a cada 5 s, conexões a cada 30 s, atividade a cada
 * 1,5 s) rodavam também com a janela minimizada, oculta, com a tela bloqueada ou o computador suspendendo:
 * ~290 processos `git` por minuto com 12 projetos, e o mesmo com o painel fora da vista (medido na
 * RAGX-0177). Este poller só decide QUANDO o ciclo roda; quanto custa cada ciclo é das RAGX-0172 e 0173.
 *
 * - Reagenda com `setTimeout` DEPOIS que `run` termina: uma execução lenta nunca empilha outra.
 * - Inativo, não executa nada (e uma execução em andamento termina, mas não reagenda).
 * - Ao voltar a ativo, executa na hora se a última execução tem mais de `intervalMs`; senão, só espera o
 *   que falta.
 */
export interface PausablePoller {
  /** Começa a agendar (ativo). A primeira execução vem depois de `intervalMs`, como o `setInterval` fazia. */
  start: () => void
  /** Para de vez e cancela o que estava agendado. */
  stop: () => void
  /** Pausa (`false`) ou retoma (`true`) sem perder o estado. */
  setActive: (active: boolean) => void
  /** Roda agora (ex.: fim de tarefa) sem esperar o intervalo; ignorado se já há uma execução em andamento. */
  runNow: () => void
  /**
   * Intervalo MAIS LONGO para o estado inativo (RAGX-0191): com `ms`, inativo deixa de ser pausa total e passa a rodar a
   * cada `ms`; `null` volta à pausa total. Só a notificação de defasagem liga isso, e desligada (padrão) a pausa da
   * RAGX-0171 continua total.
   */
  setBackgroundInterval: (ms: number | null) => void
}

export interface PausablePollerOptions {
  intervalMs: number
  run: () => Promise<unknown> | unknown
  now?: () => number
  setTimeout?: (fn: () => void, ms: number) => unknown
  clearTimeout?: (handle: unknown) => void
  /** Chamado quando `run` lança ou rejeita (nunca derruba o poller). */
  onError?: (err: unknown) => void
}

export function createPausablePoller(opts: PausablePollerOptions): PausablePoller {
  const now = opts.now ?? (() => Date.now())
  const setTimer = opts.setTimeout ?? ((fn, ms) => setTimeout(fn, ms))
  const clearTimer = opts.clearTimeout ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  let started = false
  let active = true
  let running = false
  let handle: unknown = null
  let lastRunAt = now()
  let backgroundMs: number | null = null

  const interval = () => (active ? opts.intervalMs : (backgroundMs ?? opts.intervalMs))

  function cancel(): void {
    if (handle !== null) {
      clearTimer(handle)
      handle = null
    }
  }

  function schedule(delay: number): void {
    cancel()
    if (!started || (!active && backgroundMs === null) || running) return
    handle = setTimer(tick, Math.max(0, delay))
  }

  function tick(): void {
    handle = null
    if (!started || (!active && backgroundMs === null) || running) return
    running = true
    lastRunAt = now()
    let result: Promise<unknown> | unknown
    try {
      result = opts.run()
    } catch (err) {
      opts.onError?.(err)
      result = undefined
    }
    Promise.resolve(result)
      .catch((err: unknown) => opts.onError?.(err))
      .finally(() => {
        running = false
        schedule(interval())
      })
  }

  return {
    start: () => {
      if (started) return
      started = true
      lastRunAt = now()
      schedule(opts.intervalMs)
    },
    stop: () => {
      started = false
      cancel()
    },
    setActive: (next) => {
      if (next === active) return
      active = next
      if (!active) {
        if (backgroundMs === null) cancel()
        else schedule(Math.max(0, backgroundMs - (now() - lastRunAt)))
        return
      }
      // voltou: executa na hora se já passou o intervalo, senão espera só o que falta
      const elapsed = now() - lastRunAt
      schedule(elapsed >= opts.intervalMs ? 0 : opts.intervalMs - elapsed)
    },
    runNow: () => {
      if (!started || !active || running) return
      cancel()
      tick()
    },
    setBackgroundInterval: (ms) => {
      backgroundMs = ms
      if (active || !started) return
      if (ms === null) cancel()
      else schedule(Math.max(0, ms - (now() - lastRunAt)))
    },
  }
}

import { useCallback, useRef, useSyncExternalStore } from 'react'
import { liveProjectIds } from '../activity'
import type { ActivityEvent } from '../types/ragx-bridge'

/** Um relógio por intervalo, compartilhado por todo o app: UM `setInterval` por valor de `intervalMs`, ligado só enquanto alguém assina. */
interface Clock {
  now: number
  subs: Set<() => void>
  timer: ReturnType<typeof setInterval> | null
}

const clocks = new Map<number, Clock>()

function clockFor(intervalMs: number): Clock {
  let c = clocks.get(intervalMs)
  if (!c) {
    c = { now: Date.now(), subs: new Set(), timer: null }
    clocks.set(intervalMs, c)
  }
  return c
}

function subscribeClock(intervalMs: number, listener: () => void): () => void {
  const c = clockFor(intervalMs)
  c.subs.add(listener)
  if (c.timer === null) {
    c.timer = setInterval(() => {
      c.now = Date.now()
      for (const l of [...c.subs]) l()
    }, intervalMs)
  }
  return () => {
    c.subs.delete(listener)
    if (c.subs.size === 0 && c.timer !== null) {
      clearInterval(c.timer)
      c.timer = null
    }
  }
}

function readClock(intervalMs: number): number {
  const c = clockFor(intervalMs)
  // Sem ninguém assinando o relógio não anda: o valor guardado pode estar velho. Renova uma vez (e fica estável
  // entre leituras seguidas, como o `useSyncExternalStore` exige).
  if (c.subs.size === 0 && Math.abs(Date.now() - c.now) >= intervalMs) c.now = Date.now() // `abs`: relógio do sistema acertado para trás
  return c.now
}

/** Instante atual, renovado a cada `intervalMs`. Só quem chama re-renderiza no tick. */
export function useClock(intervalMs: number): number {
  const subscribe = useCallback((l: () => void) => subscribeClock(intervalMs, l), [intervalMs])
  const get = useCallback(() => readClock(intervalMs), [intervalMs])
  return useSyncExternalStore(subscribe, get, get)
}

/**
 * Projetos com atividade no último minuto. Recalcula a cada `intervalMs`, mas só faz o componente que chama
 * re-renderizar quando a pertença muda: devolve o MESMO `Set` enquanto ela é a mesma.
 */
export function useLiveIds(activity: readonly ActivityEvent[], intervalMs = 5000): ReadonlySet<string> {
  const last = useRef<ReadonlySet<string>>(new Set())
  const subscribe = useCallback((l: () => void) => subscribeClock(intervalMs, l), [intervalMs])
  const get = useCallback(() => {
    const next = liveProjectIds(activity, Date.now())
    const prev = last.current
    if (next.size === prev.size && [...next].every((id) => prev.has(id))) return prev
    last.current = next
    return next
  }, [activity])
  return useSyncExternalStore(subscribe, get, get)
}

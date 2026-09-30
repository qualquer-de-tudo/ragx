import { useEffect, useState } from 'react'
import { mergeEvents } from '../activity'
import type { ActivityEvent } from '../types/ragx-bridge'

/**
 * Eventos de atividade das últimas 24 h, o mais novo primeiro: o que já está
 * em memória no processo principal e, depois, só o que chega por `ragx:activity`.
 */
export function useActivity(): ActivityEvent[] {
  const [events, setEvents] = useState<ActivityEvent[]>([])

  useEffect(() => {
    let alive = true
    const merge = (incoming: ActivityEvent[]) => {
      if (alive) setEvents((prev) => mergeEvents(prev, incoming, Date.now()))
    }
    window.ragx.getActivity().then(merge, (err: unknown) => console.error('getActivity() falhou:', err))
    const off = window.ragx.onActivity(merge)
    return () => {
      alive = false
      off()
    }
  }, [])

  return events
}

/** Relógio para o que muda com o tempo sem evento novo ("em uso agora" some depois de um minuto). */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}

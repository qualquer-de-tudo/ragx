import { useSyncExternalStore } from 'react'

/** Prazos dos avisos (RAGX-0180): sucesso e info somem em 4 s, erro fica 8 s para dar tempo de ler o motivo. */
export const NOTICE_MS = 4000
export const NOTICE_ERROR_MS = 8000
/** No máximo 3 na tela: o 4º tira o mais antigo. */
export const MAX_VISIBLE = 3
/** O mesmo texto, do mesmo tipo, dentro desta janela não duplica. */
export const DEDUPE_MS = 3000

export type ToastKind = 'error' | 'success' | 'info'

export interface Toast {
  id: number
  kind: ToastKind
  text: string
}

interface Live {
  toast: Toast
  /** Quanto falta para sumir; só anda enquanto o prazo corre. */
  remaining: number
  startedAt: number | null
  timer: ReturnType<typeof setTimeout> | null
}

let nextId = 1
let live: Live[] = []
let snapshot: readonly Toast[] = []
const recent = new Map<string, number>()
const listeners = new Set<() => void>()

function publish() {
  snapshot = live.map((l) => l.toast)
  for (const l of [...listeners]) l()
}

function start(l: Live) {
  l.startedAt = Date.now()
  l.timer = setTimeout(() => dismiss(l.toast.id), l.remaining)
}

/** Pausa o prazo (ponteiro ou foco em cima do aviso). */
export function pause(id: number) {
  const l = live.find((x) => x.toast.id === id)
  if (!l || l.timer === null) return
  clearTimeout(l.timer)
  l.timer = null
  l.remaining = Math.max(0, l.remaining - (Date.now() - (l.startedAt ?? Date.now())))
  l.startedAt = null
}

/** Retoma o prazo de onde parou. */
export function resume(id: number) {
  const l = live.find((x) => x.toast.id === id)
  if (!l || l.timer !== null) return
  start(l)
}

export function dismiss(id: number) {
  const l = live.find((x) => x.toast.id === id)
  if (!l) return
  if (l.timer !== null) clearTimeout(l.timer)
  live = live.filter((x) => x !== l)
  publish()
}

function show(kind: ToastKind, text: string) {
  const now = Date.now()
  const key = `${kind}:${text}`
  const last = recent.get(key)
  if (last !== undefined && now - last < DEDUPE_MS) return
  recent.set(key, now)
  for (const [k, t] of recent) if (now - t >= DEDUPE_MS) recent.delete(k)

  const l: Live = {
    toast: { id: nextId++, kind, text },
    remaining: kind === 'error' ? NOTICE_ERROR_MS : NOTICE_MS,
    startedAt: null,
    timer: null,
  }
  live = [...live, l]
  while (live.length > MAX_VISIBLE) {
    const old = live[0]
    if (old.timer !== null) clearTimeout(old.timer)
    live = live.slice(1)
  }
  start(l)
  publish()
}

export const notify = {
  error: (text: string) => show('error', text),
  success: (text: string) => show('success', text),
  info: (text: string) => show('info', text),
}

/** Zera tudo (testes). */
export function resetToasts() {
  for (const l of live) if (l.timer !== null) clearTimeout(l.timer)
  live = []
  recent.clear()
  publish()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useToasts(): readonly Toast[] {
  return useSyncExternalStore(subscribe, () => snapshot, () => snapshot)
}

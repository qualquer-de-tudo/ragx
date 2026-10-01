import type { ProjectSnapshot, Snapshot } from './types/ragx-bridge'

/**
 * Último snapshot conhecido, em `localStorage` (RAGX-0182): o painel pinta isso na hora e troca pelo vivo quando
 * chega. Só conveniência por visualizante: tudo em `try/catch`, formato validado na leitura, e sem ele o painel
 * funciona igual. O que fica guardado: nome, pasta e contagens dos projetos, só no armazenamento local do app.
 * `connectionsHealth` NÃO entra (um "tudo certo" velho enganaria).
 */
export const CACHE_KEY = 'ragx.snapshot.v1'
/** No máximo uma gravação a cada 15 s. */
export const WRITE_EVERY_MS = 15_000

let lastWrite = 0

export function resetCacheThrottle(): void {
  lastWrite = 0
}

function isProject(p: unknown): p is ProjectSnapshot {
  if (typeof p !== 'object' || p === null) return false
  const o = p as Record<string, unknown>
  const tel = o.telemetry as Record<string, unknown> | null | undefined
  return (
    typeof o.id === 'string' &&
    typeof o.name === 'string' &&
    typeof o.exists === 'boolean' &&
    typeof tel === 'object' &&
    tel !== null &&
    Array.isArray(tel.callsByTool)
  )
}

export function readCachedSnapshot(): Snapshot | null {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY)
    if (raw === null) return null
    const data: unknown = JSON.parse(raw)
    if (typeof data !== 'object' || data === null) return null
    const { v, snapshot } = data as { v?: unknown; snapshot?: unknown }
    if (v !== 1 || typeof snapshot !== 'object' || snapshot === null) return null
    const s = snapshot as { projects?: unknown; generatedAt?: unknown }
    if (typeof s.generatedAt !== 'string' || Number.isNaN(Date.parse(s.generatedAt))) return null
    if (!Array.isArray(s.projects) || !s.projects.every(isProject)) return null
    return { projects: s.projects, generatedAt: s.generatedAt }
  } catch {
    return null
  }
}

/** Grava (no máximo a cada 15 s). Hub vazio não é guardado: levaria o próximo início ao onboarding sem motivo. */
export function writeCachedSnapshot(snapshot: Snapshot, now: number = Date.now()): void {
  if (snapshot.projects.length === 0 || now - lastWrite < WRITE_EVERY_MS) return
  try {
    const { projects, generatedAt } = snapshot
    window.localStorage.setItem(CACHE_KEY, JSON.stringify({ v: 1, snapshot: { projects, generatedAt } }))
    lastWrite = now
  } catch {
    /* armazenamento cheio ou bloqueado: segue sem cache */
  }
}

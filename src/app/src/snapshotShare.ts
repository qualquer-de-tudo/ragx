import type { Snapshot } from './types/ragx-bridge'

/** Igualdade estrutural de dados vindos do IPC (JSON puro: objetos, listas, texto, número, booleano, `null`). */
export function sameData(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false
  if (Array.isArray(a) !== Array.isArray(b)) return false
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => sameData(v, b[i]))
  }
  const ka = Object.keys(a)
  const kb = Object.keys(b)
  if (ka.length !== kb.length) return false
  const ob = b as Record<string, unknown>
  return ka.every((k) => k in ob && sameData((a as Record<string, unknown>)[k], ob[k]))
}

/**
 * Lista nova que reaproveita, posição a posição por `id`, a referência de cada item inalterado; devolve `prev`
 * quando nada mudou (mesmos itens, mesma ordem). Quem usa `React.memo` só pula o render se a referência se mantém.
 */
export function shareById<T extends { id: string }>(prev: readonly T[], next: readonly T[]): readonly T[] {
  const old = new Map(prev.map((p) => [p.id, p]))
  const shared = next.map((n) => {
    const p = old.get(n.id)
    return p !== undefined && sameData(p, n) ? p : n
  })
  const unchanged = shared.length === prev.length && shared.every((s, i) => s === prev[i])
  return unchanged ? prev : shared
}

/** O que sobra do snapshot sem `generatedAt` (muda a cada 5 s) e sem os projetos (comparados à parte, um a um). */
function withoutVolatile(s: Snapshot): Record<string, unknown> {
  const out: Record<string, unknown> = { ...s }
  delete out.generatedAt
  delete out.projects
  return out
}

/**
 * O snapshot que segue valendo: `prev` quando `next` só difere em `generatedAt` (o processo principal manda um novo a
 * cada 5 s), senão um objeto novo em que cada projeto inalterado mantém a referência que já tinha.
 */
export function shareSnapshot(prev: Snapshot | null, next: Snapshot): Snapshot {
  if (prev === null) return next
  const projects = shareById(prev.projects, next.projects) as Snapshot['projects']
  if (projects === prev.projects && sameData(withoutVolatile(prev), withoutVolatile(next))) return prev
  return { ...next, projects }
}

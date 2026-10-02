/** Quantas páginas há para `total` itens (nunca menos de uma). */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize))
}

/** Mantém `page` (base 0) dentro do que existe: uma lista que encolheu não deixa a pessoa numa página vazia. */
export function clampPage(page: number, total: number, pageSize: number): number {
  return Math.min(Math.max(0, page), pageCount(total, pageSize) - 1)
}

/** Linhas por página da Atividade: o DOM fica do mesmo tamanho com 500 eventos ou com 10 mil. */
export const EVENTS_PER_PAGE = 50
export const SESSIONS_PER_PAGE = 20

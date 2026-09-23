const inteiro = new Intl.NumberFormat('pt-BR')
const compacto = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })

export function formatNumber(n: number): string {
  return inteiro.format(n)
}

export function formatCompact(n: number): string {
  return n >= 10_000 ? compacto.format(n) : inteiro.format(n)
}

export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function segmentsOf(p: string): string[] {
  return p.split(/[\\/]+/).filter(Boolean)
}

/** Pasta-mãe comum a todos os projetos (ex.: C:\projects), em segmentos. */
export function commonBase(paths: Array<string | null>): string[] {
  const all = paths.filter((p): p is string => Boolean(p)).map((p) => segmentsOf(p).slice(0, -1))
  if (all.length < 2) return []
  const base: string[] = []
  for (let i = 0; i < all[0].length; i++) {
    const seg = all[0][i].toLowerCase()
    if (!all.every((parts) => parts[i]?.toLowerCase() === seg)) break
    base.push(all[0][i])
  }
  return base
}

/** Onde o projeto mora, relativo à pasta comum — distingue "src" de outro "src". */
export function parentHint(projectPath: string | null, base: string[] = []): string | null {
  if (!projectPath) return null
  const parents = segmentsOf(projectPath).slice(0, -1)
  const rest = parents.slice(base.length)
  if (rest.length) return rest.join('/')
  return parents.length ? parents[parents.length - 1] : null
}

const STATUS_LABEL: Record<string, string> = {
  ok: 'ok',
  degraded: 'degradado',
  stale: 'desatualizado',
  missing: 'pasta ausente',
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

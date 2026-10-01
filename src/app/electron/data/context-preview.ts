import type { ContextPreview, ContextPreviewFragment } from './types'

const str = (v: unknown): string | null => (typeof v === 'string' ? v : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function parseFragment(raw: unknown): ContextPreviewFragment | null {
  if (typeof raw !== 'object' || raw === null) return null
  const f = raw as Record<string, unknown>
  const path = str(f.document_path)
  const lines = f.lines
  const tokens = num(f.tokens)
  if (path === null || tokens === null || !Array.isArray(lines) || num(lines[0]) === null || num(lines[1]) === null) return null
  // Só os campos nomeados: `content` (código) e qualquer outro ficam para trás, de propósito.
  return {
    project: str(f.project),
    documentPath: path,
    lines: [lines[0] as number, lines[1] as number],
    symbol: str(f.symbol),
    headingPath: str(f.heading_path),
    score: num(f.score) ?? 0,
    tokens,
    compressed: f.compressed === true,
    strategy: str(f.strategy),
    reason: str(f.reason),
  }
}

/**
 * Filtro de saída do preview (RAGX-0187): a resposta de `ragx context --format json` leva `query` (a pergunta de volta)
 * e `content` (código dos trechos); nenhum dos dois passa. Formato inesperado: `null`, e quem chama devolve erro.
 */
export function parseContextPreview(raw: unknown): ContextPreview | null {
  if (typeof raw !== 'object' || raw === null) return null
  const r = raw as Record<string, unknown>
  if (!Array.isArray(r.fragments)) return null
  const fragments: ContextPreviewFragment[] = []
  for (const f of r.fragments) {
    const parsed = parseFragment(f)
    if (parsed === null) return null
    fragments.push(parsed)
  }
  const byWhy = new Map<string, number>()
  if (Array.isArray(r.dropped)) {
    for (const d of r.dropped) {
      const why = typeof d === 'object' && d !== null ? str((d as Record<string, unknown>).why) : null
      byWhy.set(why ?? 'sem motivo', (byWhy.get(why ?? 'sem motivo') ?? 0) + 1)
    }
  }
  return {
    intent: str(r.intent),
    estimatedTokens: num(r.estimated_tokens) ?? 0,
    budget: num(r.budget) ?? 0,
    fragments,
    dropped: [...byWhy].map(([why, count]) => ({ why, count })),
  }
}

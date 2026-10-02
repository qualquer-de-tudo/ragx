import { formatNumber } from '../../format'
import { clampPage, pageCount } from '../../paging'

/**
 * Paginação simples: "1 a 50 de 480", Anterior e Próxima. A página é do chamador (base 0); quem usa fatia a lista
 * com `page * pageSize`. Some quando tudo cabe numa página só.
 */
export function Pager({
  total,
  page,
  pageSize,
  onPage,
  noun = 'itens',
}: {
  total: number
  page: number
  pageSize: number
  onPage: (page: number) => void
  /** O que se conta, no plural: "eventos", "sessões". */
  noun?: string
}) {
  if (total <= pageSize) return null
  const pages = pageCount(total, pageSize)
  const atual = clampPage(page, total, pageSize)
  const from = atual * pageSize + 1
  const to = Math.min(total, (atual + 1) * pageSize)
  return (
    <nav className="pager" aria-label={`Paginação de ${noun}`}>
      <p className="pager-range" role="status">
        {formatNumber(from)} a {formatNumber(to)} de {formatNumber(total)} {noun}
      </p>
      <div className="pager-buttons">
        <button type="button" className="btn btn-sm" onClick={() => onPage(0)} disabled={atual === 0} aria-label="Primeira página">
          Início
        </button>
        <button type="button" className="btn btn-sm" onClick={() => onPage(atual - 1)} disabled={atual === 0}>
          Anterior
        </button>
        <span className="pager-page dim">
          Página {formatNumber(atual + 1)} de {formatNumber(pages)}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => onPage(atual + 1)} disabled={atual >= pages - 1}>
          Próxima
        </button>
      </div>
    </nav>
  )
}

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Pager } from '../Pager'
import { clampPage, pageCount } from '../../../paging'

describe('Pager: contas', () => {
  it('páginas: nunca menos de uma, e a última pode ser parcial', () => {
    expect(pageCount(0, 50)).toBe(1)
    expect(pageCount(50, 50)).toBe(1)
    expect(pageCount(51, 50)).toBe(2)
    expect(pageCount(10_000, 50)).toBe(200)
  })

  it('clampPage segura a página dentro do que existe', () => {
    expect(clampPage(-3, 120, 50)).toBe(0)
    expect(clampPage(9, 120, 50)).toBe(2)
    expect(clampPage(1, 0, 50)).toBe(0)
  })
})

describe('Pager', () => {
  it('some quando tudo cabe numa página', () => {
    const { container } = render(<Pager total={50} page={0} pageSize={50} onPage={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('diz a faixa e a página, e Anterior/Próxima respeitam as pontas', () => {
    const onPage = vi.fn()
    const { rerender } = render(<Pager total={120} page={0} pageSize={50} onPage={onPage} noun="eventos" />)
    expect(screen.getByRole('status')).toHaveTextContent('1 a 50 de 120 eventos')
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Primeira página' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Próxima' }))
    expect(onPage).toHaveBeenCalledWith(1)

    rerender(<Pager total={120} page={2} pageSize={50} onPage={onPage} noun="eventos" />)
    expect(screen.getByRole('status')).toHaveTextContent('101 a 120 de 120 eventos')
    expect(screen.getByRole('button', { name: 'Próxima' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Anterior' }))
    expect(onPage).toHaveBeenLastCalledWith(1)
    fireEvent.click(screen.getByRole('button', { name: 'Primeira página' }))
    expect(onPage).toHaveBeenLastCalledWith(0)
  })
})

import { afterEach, describe, expect, it } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { TokenSavings } from '../TokenSavings'
import { installBridge } from '../../../test/snap'
import type { SavingsSeries } from '../../../../electron/data/types'

afterEach(cleanup)

function series(n = 14): SavingsSeries {
  const days = Array.from({ length: n }, (_, i) => ({
    date: `2026-09-${String(i + 1).padStart(2, '0')}`,
    baseline: i === 2 ? 0 : 12_000 + i * 100,
    delivered: i === 2 ? 0 : 3_000,
    calls: i === 2 ? 0 : 5,
  }))
  return {
    days,
    baseline: days.reduce((a, d) => a + d.baseline, 0),
    delivered: days.reduce((a, d) => a + d.delivered, 0),
    calls: days.reduce((a, d) => a + d.calls, 0),
  }
}

function setup() {
  installBridge()
  render(<TokenSavings projectId="p1" projectPath="C:/p1" savings={series()} />)
  const group = screen.getByRole('group', { name: /Tokens por dia/ })
  const days = () => within(group).getAllByRole('img')
  return { group, days }
}

describe('TokenSavings: gráfico por teclado (RAGX-0185)', () => {
  it('o svg é um grupo com um item por dia, cada um com nome acessível', () => {
    const { days } = setup()
    expect(days()).toHaveLength(14)
    expect(days()[0]).toHaveAttribute('aria-label', '01/09: sem RAGX 12.000, com RAGX 3.000, economia 75%')
    expect(days()[2]).toHaveAttribute('aria-label', '03/09: sem consultas')
  })

  it('só um dia entra no Tab (o último, de início) e as setas movem o ativo', () => {
    const { days } = setup()
    expect(days().filter((d) => d.getAttribute('tabindex') === '0')).toHaveLength(1)
    expect(days()[13]).toHaveAttribute('tabindex', '0')
    act(() => days()[13].focus())
    fireEvent.keyDown(days()[13], { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(days()[12])
    expect(days()[12]).toHaveAttribute('tabindex', '0')
    expect(days()[13]).toHaveAttribute('tabindex', '-1')
    fireEvent.keyDown(days()[12], { key: 'Home' })
    expect(document.activeElement).toBe(days()[0])
    fireEvent.keyDown(days()[0], { key: 'ArrowLeft' }) // sem volta: fica no primeiro
    expect(document.activeElement).toBe(days()[0])
    fireEvent.keyDown(days()[0], { key: 'End' })
    expect(document.activeElement).toBe(days()[13])
    fireEvent.keyDown(days()[13], { key: 'ArrowRight' })
    expect(document.activeElement).toBe(days()[13])
  })

  it('percorre os 14 dias só com a seta direita', () => {
    const { days } = setup()
    act(() => days()[0].focus())
    for (let i = 0; i < 13; i++) fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' })
    expect(document.activeElement).toBe(days()[13])
  })

  it('o tooltip aparece no foco e some ao sair, como no hover', () => {
    const { days } = setup()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    act(() => days()[0].focus())
    expect(screen.getByRole('status')).toHaveTextContent('Arquivos inteiros')
    fireEvent.keyDown(days()[0], { key: 'ArrowRight' })
    act(() => days()[1].focus())
    act(() => days()[1].blur())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('dia sem consulta diz "sem consultas" no tooltip', () => {
    const { days } = setup()
    act(() => days()[2].focus())
    expect(screen.getByRole('status')).toHaveTextContent('sem consultas')
  })

  it('outras teclas não fazem nada e o hover continua valendo', () => {
    const { days } = setup()
    act(() => days()[5].focus())
    fireEvent.keyDown(days()[5], { key: 'a' })
    expect(document.activeElement).toBe(days()[5])
    fireEvent.mouseEnter(days()[7])
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('a tabela alternativa (Ver em tabela) continua', () => {
    setup()
    const details = screen.getByText('Ver em tabela').closest('details')
    expect(details).not.toBeNull()
    expect(within(details!).getByRole('table')).toBeInTheDocument()
  })
})


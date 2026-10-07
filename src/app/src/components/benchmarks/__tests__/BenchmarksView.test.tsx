import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { BenchmarksView } from '../BenchmarksView'
import { benchmarks } from '../../../benchmarks'

describe('BenchmarksView', () => {
  it('mostra cada métrica com valor atual, antes, variação e meta', () => {
    render(<BenchmarksView />)
    const card = screen.getByRole('article', { name: 'Contexto entregue por consulta' })
    expect(within(card).getByText('2.958 tokens')).toBeInTheDocument()
    expect(within(card).getByText('−62%')).toBeInTheDocument()
    expect(within(card).getByText('Antes: 7.684 tokens')).toBeInTheDocument()
    expect(within(card).getByText(/Meta até 3\.200 tokens/)).toHaveTextContent('atingida')
    expect(screen.getAllByRole('article')).toHaveLength(benchmarks.metrics.length)
  })

  it('a meta não atingida aparece como tal, com o motivo', () => {
    render(<BenchmarksView />)
    const card = screen.getByRole('article', { name: 'Índice sem mudança, 20 mil arquivos' })
    expect(within(card).getByText(/Meta até 1,5 s/)).toHaveTextContent('não atingida')
    expect(within(card).getByText(/sem atalho seguro/)).toBeInTheDocument()
  })

  it('sem linha de base mostra o motivo em vez de uma variação inventada', () => {
    render(<BenchmarksView />)
    const card = screen.getByRole('article', { name: 'Edição não commitada visível na busca' })
    expect(within(card).getByText(/Antes: indefinida/)).toBeInTheDocument()
    expect(within(card).queryByText(/%/)).not.toBeInTheDocument()
  })

  it('a medição contra um agente sem RAGX mostra o veredito inconclusivo e a tabela', () => {
    render(<BenchmarksView />)
    const sec = within(screen.getByRole('region', { name: 'Contra um agente sem RAGX, no seu projeto' }))
    expect(sec.getByText(/Inconclusivo em tokens faturáveis/)).toBeInTheDocument()
    expect(sec.getByRole('row', { name: /Tokens faturáveis.*27\.569.*26\.040/ })).toBeInTheDocument()
    expect(sec.getByRole('row', { name: /Turnos.*6.*3/ })).toBeInTheDocument()
  })

  it('a qualidade da busca traz o recall com duas casas e o intervalo', () => {
    render(<BenchmarksView />)
    const sec = within(screen.getByRole('region', { name: 'Qualidade da busca' }))
    expect(sec.getByRole('row', { name: /MiniLM.*0,62.*0,54 a 0,70.*0,60.*0,51 a 0,68/ })).toBeInTheDocument()
    expect(sec.getByRole('row', { name: /nomic-embed-text.*0,71.*0,65/ })).toBeInTheDocument()
  })

  it('a linha do tempo vai do mais novo ao mais antigo, com as versões', () => {
    render(<BenchmarksView />)
    const eventos = within(screen.getByRole('region', { name: 'Linha do tempo' })).getAllByRole('heading', { level: 4 })
    expect(eventos.map((e) => e.textContent)).toEqual([...benchmarks.timeline].reverse().map((e) => e.title))
    expect(eventos[eventos.length - 1]).toHaveTextContent('A auditoria mede a linha de base')
    expect(screen.getByText(/versão 1\.0\.0-beta\.5/)).toBeInTheDocument()
  })

  it('o resumo conta as metas atingidas', () => {
    render(<BenchmarksView />)
    expect(screen.getByText('10 de 11 metas atingidas')).toBeInTheDocument()
  })
})

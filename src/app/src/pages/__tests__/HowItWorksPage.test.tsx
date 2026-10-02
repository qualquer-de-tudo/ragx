import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { HowItWorksPage } from '../HowItWorksPage'
import { HOW_IT_WORKS, HOW_KEEPS, HOW_LOCAL, HOW_STEPS } from '../../components/onboarding/howItWorks'

describe('HowItWorksPage', () => {
  it('mostra o caminho do dado em cinco passos numerados, na ordem', () => {
    render(<HowItWorksPage onRestart={() => {}} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Como funciona' })).toBeInTheDocument()
    const passos = within(screen.getByRole('region', { name: 'O caminho do dado' })).getAllByRole('listitem')
    expect(passos).toHaveLength(5)
    expect(HOW_STEPS.map((s) => s.title)).toEqual(['Seu código', 'Security Gate', 'Índice', 'MCP', 'Claude Code'])
    HOW_STEPS.forEach((s, i) => {
      expect(passos[i]).toHaveTextContent(s.title)
      expect(passos[i]).toHaveTextContent(s.text)
      expect(passos[i]).toHaveTextContent(String(i + 1))
    })
  })

  it('explica o que mantém o índice em dia e onde ficam os dados', () => {
    render(<HowItWorksPage onRestart={() => {}} />)
    const keeps = within(screen.getByRole('region', { name: 'O que mantém o índice em dia' }))
    for (const k of HOW_KEEPS) {
      expect(keeps.getByText(k.title)).toBeInTheDocument()
      expect(keeps.getByText(k.text)).toBeInTheDocument()
    }
    const local = within(screen.getByRole('region', { name: 'Onde ficam seus dados' }))
    for (const t of HOW_LOCAL) expect(local.getByText(t)).toBeInTheDocument()
  })

  it('"Refazer configuração" chama onRestart e "Ver os hooks em Conexões" leva para Conexões', () => {
    const onRestart = vi.fn()
    const onOpenConnections = vi.fn()
    render(<HowItWorksPage onRestart={onRestart} onOpenConnections={onOpenConnections} />)
    fireEvent.click(screen.getByRole('button', { name: 'Refazer configuração' }))
    expect(onRestart).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Ver os hooks em Conexões' }))
    expect(onOpenConnections).toHaveBeenCalledTimes(1)
  })

  it('sem onOpenConnections o atalho não aparece', () => {
    render(<HowItWorksPage onRestart={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Ver os hooks em Conexões' })).not.toBeInTheDocument()
  })

  it('o texto corrido do onboarding continua com cinco parágrafos', () => {
    expect(HOW_IT_WORKS).toHaveLength(5)
  })
})

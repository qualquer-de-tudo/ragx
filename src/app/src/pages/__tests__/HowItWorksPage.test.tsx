import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { HowItWorksPage } from '../HowItWorksPage'
import { HOW_IT_WORKS } from '../../components/onboarding/howItWorks'

describe('HowItWorksPage', () => {
  it('mostra o texto do passo 1 do onboarding e "Refazer configuração" chama onRestart', () => {
    const onRestart = vi.fn()
    render(<HowItWorksPage onRestart={onRestart} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Como funciona' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Como o RAGX funciona' })).toBeInTheDocument()
    expect(HOW_IT_WORKS).toHaveLength(5)
    for (const p of HOW_IT_WORKS) expect(screen.getByText(p)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Refazer configuração' }))
    expect(onRestart).toHaveBeenCalledTimes(1)
  })
})

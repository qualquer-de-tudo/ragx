import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ProjectsPage } from '../pages/ProjectsPage'
import { ActivityPage } from '../pages/ActivityPage'
import { installBridge, snap } from '../test/snap'

afterEach(cleanup)

// RAGX-0185: todo `role="radiogroup"` do app responde a seta, Home e End, e só o marcado está no Tab.
function percorre(group: HTMLElement) {
  const radios = () => within(group).getAllByRole('radio')
  expect(radios().filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1)
  const n = radios().length
  expect(n).toBeGreaterThan(1)
  const marked = () => radios().findIndex((r) => r.getAttribute('aria-checked') === 'true')

  radios()[marked()].focus()
  fireEvent.keyDown(document.activeElement!, { key: 'Home' })
  expect(marked()).toBe(0)
  expect(document.activeElement).toBe(radios()[0])
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' })
  expect(marked()).toBe(1)
  fireEvent.keyDown(document.activeElement!, { key: 'End' })
  expect(marked()).toBe(n - 1)
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' }) // dá a volta
  expect(marked()).toBe(0)
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' }) // dá a volta para trás
  expect(marked()).toBe(n - 1)
  expect(radios().filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1)
}

describe('grupos de rádio do app', () => {
  it('Projetos: Filtrar e Visualização', () => {
    installBridge()
    render(<ProjectsPage projects={[snap({ id: 'a', name: 'A' })]} jobs={[]} query="" onOpen={vi.fn()} />)
    const groups = screen.getAllByRole('radiogroup')
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual(['Filtrar projetos', 'Visualização'])
    for (const g of groups) percorre(g)
  })

  it('Atividade: Tipo de atividade', () => {
    installBridge()
    render(<ActivityPage events={[]} projects={[]} jobs={[]} now={Date.now()} onOpen={vi.fn()} />)
    const groups = screen.getAllByRole('radiogroup')
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual(['Tipo de atividade'])
    percorre(groups[0])
  })
})

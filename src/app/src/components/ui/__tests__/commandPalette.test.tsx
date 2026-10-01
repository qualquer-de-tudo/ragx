import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CommandPalette } from '..'
import { buildCommands, type Command } from '../../../commands'
import { snap } from '../../../test/snap'

afterEach(cleanup)

const projects = [
  snap({ id: 'juriflux', name: 'Juriflux' }),
  snap({ id: 'gone', name: 'Sumido', exists: false }),
  snap({ id: 'ragx', name: 'ragx' }),
]

function setup() {
  const onRun = vi.fn<(c: Command) => void>()
  const onClose = vi.fn()
  render(<CommandPalette commands={buildCommands(projects)} onRun={onRun} onClose={onClose} />)
  return { onRun, onClose, input: screen.getByRole('combobox', { name: 'Buscar comando' }) }
}

describe('CommandPalette', () => {
  it('é um combobox com lista; o foco começa no campo', () => {
    const { input } = setup()
    expect(document.activeElement).toBe(input)
    expect(input).toHaveAttribute('aria-expanded', 'true')
    const list = screen.getByRole('listbox', { name: 'Comandos' })
    expect(input).toHaveAttribute('aria-controls', list.id)
    expect(screen.getAllByRole('option').length).toBeGreaterThan(0)
  })

  it('digitar "jur" mostra Juriflux e Enter executa o primeiro (abrir)', () => {
    const { input, onRun, onClose } = setup()
    fireEvent.change(input, { target: { value: 'jur' } })
    expect(screen.getByRole('option', { name: /Abrir Juriflux/ })).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRun).toHaveBeenCalledTimes(1)
    expect(onRun.mock.calls[0][0].action).toEqual({ type: 'route', route: { page: 'project', id: 'juriflux' } })
    expect(onClose).toHaveBeenCalled()
  })

  it('setas movem a opção ativa (aria-activedescendant e aria-selected), com volta ao fim', () => {
    const { input } = setup()
    fireEvent.change(input, { target: { value: 'ir para' } })
    const options = () => screen.getAllByRole('option')
    expect(options()).toHaveLength(4)
    expect(input).toHaveAttribute('aria-activedescendant', options()[0].id)
    expect(options()[0]).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input).toHaveAttribute('aria-activedescendant', options()[1].id)
    expect(options()[1]).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    fireEvent.keyDown(input, { key: 'ArrowUp' }) // volta ao fim
    expect(input).toHaveAttribute('aria-activedescendant', options()[3].id)
    fireEvent.keyDown(input, { key: 'Home' })
    expect(input).toHaveAttribute('aria-activedescendant', options()[0].id)
    fireEvent.keyDown(input, { key: 'End' })
    expect(input).toHaveAttribute('aria-activedescendant', options()[3].id)
  })

  it('"Atualizar Juriflux" entrega exatamente { kind: update, projectId: juriflux }', () => {
    const { input, onRun } = setup()
    fireEvent.change(input, { target: { value: 'atualizar jur' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRun.mock.calls[0][0].action).toStrictEqual({ type: 'job', kind: 'update', projectId: 'juriflux' })
  })

  it('projeto sem pasta aparece desabilitado e não executa', () => {
    const { input, onRun, onClose } = setup()
    fireEvent.change(input, { target: { value: 'atualizar sumido' } })
    const opt = screen.getByRole('option', { name: /Atualizar Sumido/ })
    expect(opt).toHaveAttribute('aria-disabled', 'true')
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.click(opt)
    expect(onRun).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('a contagem de resultados muda com o filtro (região aria-live)', () => {
    const { input } = setup()
    const live = () => screen.getByText(/resultado/)
    fireEvent.change(input, { target: { value: 'ir para' } })
    expect(live()).toHaveTextContent('4 resultados')
    fireEvent.change(input, { target: { value: 'jur' } })
    expect(live()).toHaveTextContent(/resultados?$/)
    fireEvent.change(input, { target: { value: 'zzzz' } })
    expect(live()).toHaveTextContent('Nenhum resultado')
    expect(live().closest('[aria-live]')).not.toBeNull()
    expect(screen.queryAllByRole('option')).toHaveLength(0)
  })

  it('Esc fecha', () => {
    const { input, onClose } = setup()
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

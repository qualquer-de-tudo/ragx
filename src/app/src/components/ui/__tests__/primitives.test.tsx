import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { EmptyState, Icon, IconButton, Modal, Segmented, Switch, Tooltip } from '..'

afterEach(cleanup)

function Group({ onChange = () => {} }: { onChange?: (v: string) => void }) {
  const [v, setV] = useState('a')
  return (
    <Segmented
      label="Grupo"
      value={v}
      options={[
        { value: 'a', label: 'A' },
        { value: 'b', label: 'B' },
        { value: 'c', label: 'C' },
      ]}
      onChange={(next) => {
        setV(next)
        onChange(next)
      }}
    />
  )
}

describe('Segmented', () => {
  it('só o item marcado entra na ordem do Tab', () => {
    render(<Group />)
    const [a, b, c] = screen.getAllByRole('radio')
    expect([a, b, c].map((r) => r.getAttribute('tabindex'))).toEqual(['0', '-1', '-1'])
    expect(a).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radiogroup', { name: 'Grupo' })).toBeInTheDocument()
  })

  it('setas, Home e End mudam a escolha e levam o foco', () => {
    const onChange = vi.fn()
    render(<Group onChange={onChange} />)
    const radios = () => screen.getAllByRole('radio')
    radios()[0].focus()
    fireEvent.keyDown(radios()[0], { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith('b')
    expect(document.activeElement).toBe(radios()[1])
    expect(radios()[1]).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(radios()[1], { key: 'End' })
    expect(onChange).toHaveBeenLastCalledWith('c')
    fireEvent.keyDown(radios()[2], { key: 'ArrowRight' }) // dá a volta
    expect(onChange).toHaveBeenLastCalledWith('a')
    fireEvent.keyDown(radios()[0], { key: 'ArrowLeft' }) // dá a volta para trás
    expect(onChange).toHaveBeenLastCalledWith('c')
    fireEvent.keyDown(radios()[2], { key: 'Home' })
    expect(onChange).toHaveBeenLastCalledWith('a')
  })

  it('clique escolhe', () => {
    const onChange = vi.fn()
    render(<Group onChange={onChange} />)
    fireEvent.click(screen.getByRole('radio', { name: 'C' }))
    expect(onChange).toHaveBeenCalledWith('c')
  })
})

describe('Switch', () => {
  it('clique chama onChange com o valor novo; o nome vem do label', () => {
    const onChange = vi.fn()
    render(<Switch checked={false} label="Hooks" onChange={onChange} />)
    const sw = screen.getByRole('switch', { name: 'Hooks' })
    expect(sw).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(sw)
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('o nome pode vir de labelledBy; desabilitado não age', () => {
    const onChange = vi.fn()
    render(
      <>
        <h2 id="t">Título</h2>
        <Switch checked labelledBy="t" disabled onChange={onChange} />
      </>,
    )
    const sw = screen.getByRole('switch', { name: 'Título' })
    expect(sw).toBeDisabled()
    fireEvent.click(sw)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('é um botão: Espaço e Enter ativam pelo clique do navegador', () => {
    render(<Switch checked label="x" onChange={() => {}} />)
    expect(screen.getByRole('switch').tagName).toBe('BUTTON')
  })
})

describe('Modal', () => {
  it('foco inicial dentro, Tab preso, Esc fecha e o foco volta a quem abriu', () => {
    const onClose = vi.fn()
    function Host() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button onClick={() => setOpen(true)}>abrir</button>
          {open && (
            <Modal
              title="Janela"
              onClose={() => {
                onClose()
                setOpen(false)
              }}
            >
              <button>dentro</button>
            </Modal>
          )}
        </>
      )
    }
    render(<Host />)
    const opener = screen.getByRole('button', { name: 'abrir' })
    opener.focus()
    fireEvent.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Janela' })
    expect(dialog.contains(document.activeElement)).toBe(true)
    // Tab no último volta ao primeiro (Fechar, depois "dentro")
    screen.getByRole('button', { name: 'dentro' }).focus()
    fireEvent.keyDown(dialog, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Fechar' }))
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(opener)
  })

  it('clique no fundo fecha; clique dentro não', () => {
    const onClose = vi.fn()
    const { container } = render(
      <Modal title="J" onClose={onClose}>
        <p>conteúdo</p>
      </Modal>,
    )
    fireEvent.mouseDown(screen.getByText('conteúdo'))
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.mouseDown(container.querySelector('.modal-backdrop')!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('Icon e IconButton', () => {
  it('o ícone é decorativo', () => {
    const { container } = render(<Icon name="search" />)
    const svg = container.querySelector('svg')!
    expect(svg).toHaveAttribute('aria-hidden', 'true')
    expect(svg).toHaveAttribute('focusable', 'false')
  })

  it('IconButton tem nome pelo label e clica', () => {
    const onClick = vi.fn()
    render(<IconButton label="Voltar" icon="back" onClick={onClick} />)
    fireEvent.click(screen.getByRole('button', { name: 'Voltar' }))
    expect(onClick).toHaveBeenCalled()
  })

  it('IconButton sem label não compila', () => {
    // @ts-expect-error `label` é obrigatório
    const el = <IconButton icon="back" onClick={() => {}} />
    expect(el).toBeTruthy()
  })
})

describe('EmptyState', () => {
  it('é um status com o texto', () => {
    render(<EmptyState title="Vazio">Nada aqui.</EmptyState>)
    const s = screen.getByRole('status')
    expect(s).toHaveTextContent('Vazio')
    expect(s).toHaveTextContent('Nada aqui.')
  })
})

describe('Tooltip', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  const ui = (
    <Tooltip text="Dica longa" focusable>
      {(tip) => <span {...tip}>gatilho</span>}
    </Tooltip>
  )

  it('abre no foco, liga por aria-describedby e fecha com Esc', () => {
    render(ui)
    const trigger = screen.getByText('gatilho')
    expect(trigger).toHaveAttribute('tabindex', '0')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => trigger.focus())
    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent('Dica longa')
    expect(trigger).toHaveAttribute('aria-describedby', tip.id)
    fireEvent.keyDown(trigger, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(trigger).not.toHaveAttribute('aria-describedby')
  })

  it('no mouse abre depois do atraso e fecha ao sair', () => {
    render(ui)
    const trigger = screen.getByText('gatilho')
    fireEvent.mouseEnter(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(450)
    })
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.mouseLeave(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('sair antes do atraso cancela', () => {
    render(ui)
    const trigger = screen.getByText('gatilho')
    fireEvent.mouseEnter(trigger)
    fireEvent.mouseLeave(trigger)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})

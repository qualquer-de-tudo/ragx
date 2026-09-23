import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AddProjectDialog } from '../AddProjectDialog'
import { installBridge } from '../../../test/snap'
import type { DiscoverResult } from '../../../types/ragx-bridge'

const FOLDER = { token: 'tok-root', path: 'C:/projects' }

const TWO_FOUND: DiscoverResult = {
  items: [
    { token: 'tok-a', path: 'C:/projects/juriflux', name: 'juriflux', alreadyRegistered: false },
    { token: 'tok-b', path: 'C:/projects/ragx', name: 'ragx', alreadyRegistered: true },
  ],
  truncated: false,
}

function setup(discover: DiscoverResult = TWO_FOUND) {
  const b = installBridge({
    pickFolder: vi.fn().mockResolvedValue(FOLDER),
    discover: vi.fn().mockResolvedValue(discover),
  })
  const onClose = vi.fn()
  render(<AddProjectDialog open onClose={onClose} />)
  return { b, onClose, dialog: screen.getByRole('dialog', { name: 'Adicionar projeto' }) }
}

async function chooseFolder() {
  fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
  await screen.findByText(FOLDER.path)
}

describe('AddProjectDialog', () => {
  it('fechado não renderiza nada', () => {
    installBridge()
    render(<AddProjectDialog open={false} onClose={vi.fn()} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('é um diálogo modal', () => {
    const { dialog } = setup()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('fluxo completo: 2 encontrados (1 já no painel), hooks marcados, um add-project', async () => {
    const { b, onClose } = setup()
    await chooseFolder()
    expect(b.discover).toHaveBeenCalledWith('tok-root')

    const fresh = await screen.findByRole('checkbox', { name: /juriflux/ })
    const registered = screen.getByRole('checkbox', { name: /ragx/ })
    expect(fresh).toBeChecked()
    expect(registered).not.toBeChecked()
    expect(registered).toBeDisabled()
    expect(screen.getByText('já está no painel')).toBeInTheDocument()

    const hooks = screen.getByRole('checkbox', {
      name: 'Instalar hooks de git (mantém o índice na branch em que você está)',
    })
    expect(hooks).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: 'Adicionar 1 projeto' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(b.enqueueJob).toHaveBeenCalledTimes(1)
    expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'add-project', folderToken: 'tok-a', installHooks: true })
  })

  it('um add-project por item marcado, respeitando o checkbox de hooks', async () => {
    const { b, onClose } = setup({
      items: [
        { token: 'tok-a', path: 'C:/projects/a', name: 'a', alreadyRegistered: false },
        { token: 'tok-b', path: 'C:/projects/b', name: 'b', alreadyRegistered: false },
        { token: 'tok-c', path: 'C:/projects/c', name: 'c', alreadyRegistered: false },
      ],
      truncated: false,
    })
    await chooseFolder()
    fireEvent.click(await screen.findByRole('checkbox', { name: /^b/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Instalar hooks de git/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar 2 projetos' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(b.enqueueJob).toHaveBeenCalledTimes(2)
    expect(b.enqueueJob).toHaveBeenNthCalledWith(1, { kind: 'add-project', folderToken: 'tok-a', installHooks: false })
    expect(b.enqueueJob).toHaveBeenNthCalledWith(2, { kind: 'add-project', folderToken: 'tok-c', installHooks: false })
  })

  it('nada encontrado: oferece usar a própria pasta como projeto novo', async () => {
    const { b, onClose } = setup({ items: [], truncated: false })
    await chooseFolder()
    const own = await screen.findByRole('checkbox', { name: 'Usar esta pasta como um projeto novo' })
    const add = screen.getByRole('button', { name: 'Adicionar 0 projetos' })
    expect(add).toBeDisabled()

    fireEvent.click(own)
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar 1 projeto' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(b.enqueueJob).toHaveBeenCalledWith({ kind: 'add-project', folderToken: 'tok-root', installHooks: true })
  })

  it('escolha de pasta cancelada não muda nada', async () => {
    const b = installBridge({ pickFolder: vi.fn().mockResolvedValue(null) })
    render(<AddProjectDialog open onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    await waitFor(() => expect(b.pickFolder).toHaveBeenCalled())
    await act(async () => {})
    expect(b.discover).not.toHaveBeenCalled()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Adicionar 0 projetos' })).toBeDisabled()
  })

  it('busca parcial avisa que a pasta é grande demais', async () => {
    setup({ ...TWO_FOUND, truncated: true })
    await chooseFolder()
    expect(
      await screen.findByText(
        'Busca parcial: a pasta é grande demais para varrer inteira. Escolha uma pasta mais específica se faltar algum projeto.',
      ),
    ).toBeInTheDocument()
  })

  it('falha ao procurar projetos aparece como mensagem, sem quebrar', async () => {
    installBridge({
      pickFolder: vi.fn().mockResolvedValue(FOLDER),
      discover: vi.fn().mockRejectedValue(new Error('boom')),
    })
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<AddProjectDialog open onClose={vi.fn()} />)
    await chooseFolder()
    expect(await screen.findByText('Não foi possível procurar projetos nesta pasta.')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('falha ao enfileirar mantém o diálogo aberto com o aviso', async () => {
    const { b, onClose } = setup()
    vi.mocked(b.enqueueJob).mockRejectedValueOnce(new Error('recusado'))
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    await chooseFolder()
    fireEvent.click(await screen.findByRole('button', { name: 'Adicionar 1 projeto' }))
    expect(await screen.findByText('Não foi possível adicionar juriflux.')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('Esc fecha', () => {
    const { onClose, dialog } = setup()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('"Cancelar" e o botão de fechar fecham', () => {
    const { onClose } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('prende o foco dentro do diálogo e começa em "Escolher pasta"', () => {
    const { dialog } = setup()
    const pick = within(dialog).getByRole('button', { name: 'Escolher pasta' })
    expect(pick).toHaveFocus()

    const focusables = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled])'))
    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    last.focus()
    fireEvent.keyDown(dialog, { key: 'Tab' })
    expect(first).toHaveFocus()

    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()
  })

  it('devolve o foco para quem abriu ao fechar', () => {
    installBridge()
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const { rerender } = render(<AddProjectDialog open onClose={vi.fn()} />)
    expect(opener).not.toHaveFocus()
    rerender(<AddProjectDialog open={false} onClose={vi.fn()} />)
    expect(opener).toHaveFocus()
    opener.remove()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AddProjectDialog } from '../AddProjectDialog'
import { installBridge } from '../../../test/snap'
import type { DiscoverItem, DiscoverResult } from '../../../types/ragx-bridge'

const FOLDER = { token: 'tok-root', path: 'C:/projects' }

const TWO_FOUND: DiscoverResult = {
  items: [
    { token: 'tok-a', path: 'C:/projects/juriflux', name: 'juriflux', alreadyRegistered: false, isNew: false },
    { token: 'tok-b', path: 'C:/projects/ragx', name: 'ragx', alreadyRegistered: true, isNew: false },
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
  await screen.findByText(FOLDER.path, { selector: '.add-flow-path' })
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
        { token: 'tok-a', path: 'C:/projects/a', name: 'a', alreadyRegistered: false, isNew: false },
        { token: 'tok-b', path: 'C:/projects/b', name: 'b', alreadyRegistered: false, isNew: false },
        { token: 'tok-c', path: 'C:/projects/c', name: 'c', alreadyRegistered: false, isNew: false },
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
    const own = await screen.findByRole('checkbox', { name: /Usar esta pasta como um projeto novo/ })
    expect(own).not.toBeChecked()
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

describe('AddProjectDialog - repositórios novos e várias pastas', () => {
  function item(token: string, name: string, over: Partial<DiscoverItem> = {}): DiscoverItem {
    return { token, path: `C:/${name}`, name, alreadyRegistered: false, isNew: false, ...over }
  }

  it('repositório git sem ragx.toml aparece com a marca "novo" e começa desmarcado; projeto do RAGX começa marcado', async () => {
    setup({
      items: [item('tok-a', 'antigo'), item('tok-n', 'repo-novo', { isNew: true })],
      truncated: false,
    })
    await chooseFolder()

    const fresh = await screen.findByRole('checkbox', { name: /repo-novo/ })
    expect(fresh).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /antigo/ })).toBeChecked()
    const li = fresh.closest('li') as HTMLElement
    expect(within(li).getByText('novo')).toBeInTheDocument()
    expect(within(screen.getByRole('checkbox', { name: /antigo/ }).closest('li') as HTMLElement).queryByText('novo')).toBeNull()
  })

  it('cada "Escolher pasta" soma à lista, sem repetir o que já estava nela, e todos entram no add-project', async () => {
    const b = installBridge({
      pickFolder: vi
        .fn()
        .mockResolvedValueOnce({ token: 'root-1', path: 'C:/um' })
        .mockResolvedValueOnce({ token: 'root-2', path: 'C:/dois' }),
      discover: vi
        .fn()
        .mockResolvedValueOnce({ items: [item('t1', 'alfa'), item('t2', 'beta', { isNew: true })], truncated: false })
        // A segunda pasta devolve "alfa" de novo (token novo, mesmo caminho) e um projeto novo.
        .mockResolvedValueOnce({ items: [item('t3', 'alfa'), item('t4', 'gama')], truncated: false }),
    })
    const onClose = vi.fn()
    render(<AddProjectDialog open onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    await screen.findByRole('checkbox', { name: /beta/ })
    fireEvent.click(screen.getByRole('checkbox', { name: /beta/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    await screen.findByRole('checkbox', { name: /gama/ })

    expect(screen.getAllByRole('checkbox', { name: /alfa/ })).toHaveLength(1)
    expect(screen.getByRole('checkbox', { name: /beta/ })).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: 'Adicionar 3 projetos' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(vi.mocked(b.enqueueJob).mock.calls.map((c) => c[0].folderToken)).toEqual(['t1', 't2', 't4'])
  })

  it('cada item pode sair da lista', async () => {
    setup({ items: [item('tok-a', 'a'), item('tok-b', 'b')], truncated: false })
    await chooseFolder()
    await screen.findByRole('checkbox', { name: /^a/ })

    fireEvent.click(screen.getByRole('button', { name: 'Remover a da lista' }))

    expect(screen.queryByRole('checkbox', { name: /^a/ })).toBeNull()
    expect(screen.getByRole('button', { name: 'Adicionar 1 projeto' })).toBeEnabled()
  })

  it('a própria pasta como projeto novo só aparece quando a escolha não achou nada', async () => {
    installBridge({
      pickFolder: vi
        .fn()
        .mockResolvedValueOnce({ token: 'root-1', path: 'C:/com-projetos' })
        .mockResolvedValueOnce({ token: 'root-2', path: 'C:/vazia' }),
      discover: vi
        .fn()
        .mockResolvedValueOnce({ items: [item('t1', 'alfa')], truncated: false })
        .mockResolvedValueOnce({ items: [], truncated: false }),
    })
    render(<AddProjectDialog open onClose={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    await screen.findByRole('checkbox', { name: /alfa/ })
    expect(screen.queryByRole('checkbox', { name: /Usar esta pasta como um projeto novo/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    const own = await screen.findByRole('checkbox', { name: /Usar esta pasta como um projeto novo/ })
    expect(own).not.toBeChecked()
    // A lista anterior continua lá.
    expect(screen.getByRole('checkbox', { name: /alfa/ })).toBeChecked()
  })
})

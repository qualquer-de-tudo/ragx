import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ContextPreview } from '../ContextPreview'
import { installBridge } from '../../../test/snap'
import type { ContextPreview as Preview } from '../../../types/ragx-bridge'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const result: Preview = {
  intent: 'implementar',
  estimatedTokens: 1200,
  budget: 3000,
  fragments: [
    { project: 'p', documentPath: 'src/pedido.py', lines: [10, 30], symbol: 'criar_pedido', headingPath: null, score: 0.9, tokens: 400, compressed: false, strategy: 'full', reason: 'semântico' },
    { project: 'p', documentPath: 'docs/a.md', lines: [1, 5], symbol: null, headingPath: 'Visão', score: 0.5, tokens: 80, compressed: true, strategy: 'sig', reason: null },
  ],
  dropped: [{ why: 'orçamento', count: 3 }],
}

async function ask(text: string) {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } })
  await act(async () => {
    fireEvent.submit(screen.getByRole('textbox').closest('form')!)
  })
}

describe('ContextPreview', () => {
  it('mostra trechos, tokens, intenção e descartes; a pergunta vai com o projectId', async () => {
    const b = installBridge({ previewContext: vi.fn().mockResolvedValue(result) })
    render(<ContextPreview projectId="p1" />)
    await ask('como o pedido é criado?')
    expect(b.previewContext).toHaveBeenCalledWith('p1', 'como o pedido é criado?')
    expect(screen.getByText(/2 trecho\(s\) · 1\.200 de 3\.000 tokens · intenção implementar/)).toBeInTheDocument()
    expect(screen.getByText('src/pedido.py:10-30')).toBeInTheDocument()
    expect(screen.getByText(/criar_pedido · 400 tokens · semântico/)).toBeInTheDocument()
    expect(screen.getByText(/Visão · 80 tokens · comprimido/)).toBeInTheDocument()
    expect(screen.getByText(/3 por orçamento/)).toBeInTheDocument()
  })

  it('vazio e erro', async () => {
    installBridge({ previewContext: vi.fn().mockResolvedValueOnce({ ...result, fragments: [], dropped: [] }).mockRejectedValueOnce(new Error("Error invoking remote method 'ragx:previewContext': Error: embedder fora")) })
    render(<ContextPreview projectId="p1" />)
    await ask('x')
    expect(screen.getByText('Nenhum trecho do índice responde a essa pergunta.')).toBeInTheDocument()
    await ask('y')
    expect(screen.getByText('Não foi possível montar o contexto: embedder fora')).toBeInTheDocument()
  })

  it('carregando mostra o aviso da primeira busca', async () => {
    installBridge({ previewContext: vi.fn(() => new Promise<Preview>(() => {})) })
    render(<ContextPreview projectId="p1" />)
    await ask('x')
    expect(screen.getAllByText(/A primeira busca pode levar alguns segundos/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Pré-visualizar' })).toBeDisabled()
  })

  it('não roda por tecla digitada nem com texto vazio', () => {
    const b = installBridge()
    render(<ContextPreview projectId="p1" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'abc' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'a' })
    expect(b.previewContext).not.toHaveBeenCalled()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: 'Pré-visualizar' })).toBeDisabled()
  })

  it('a pergunta nunca vai para o armazenamento do navegador, e o campo tem os atributos de privacidade', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    installBridge({ previewContext: vi.fn().mockResolvedValue(result) })
    render(<ContextPreview projectId="p1" />)
    await ask('SENTINELA-0187')
    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('autocomplete', 'off')
    expect(input).toHaveAttribute('spellcheck', 'false')
    expect(input).toHaveAttribute('maxlength', '500')
    expect(input).not.toHaveAttribute('name')
    expect(setItem.mock.calls.flat().join(' ')).not.toContain('SENTINELA-0187')
  })

  it('Limpar apaga a pergunta e o resultado; trocar de projeto (key) recomeça do zero', async () => {
    installBridge({ previewContext: vi.fn().mockResolvedValue(result) })
    const { rerender } = render(<ContextPreview key="a" projectId="a" />)
    await ask('x')
    fireEvent.click(screen.getByRole('button', { name: 'Limpar' }))
    expect(screen.getByRole('textbox')).toHaveValue('')
    expect(screen.queryByText(/trecho\(s\)/)).not.toBeInTheDocument()
    await ask('y')
    rerender(<ContextPreview key="b" projectId="b" />)
    expect(screen.getByRole('textbox')).toHaveValue('')
    expect(screen.queryByText(/trecho\(s\)/)).not.toBeInTheDocument()
  })
})

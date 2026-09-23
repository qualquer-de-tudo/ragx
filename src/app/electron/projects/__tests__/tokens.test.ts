import { describe, expect, it } from 'vitest'
import { FolderTokens } from '../tokens'

describe('FolderTokens', () => {
  it('token desconhecido devolve undefined', () => {
    const tokens = new FolderTokens()
    expect(tokens.get('nao-existe')).toBeUndefined()
  })

  it('issue devolve um token que resolve para o caminho', () => {
    const tokens = new FolderTokens()
    const token = tokens.issue('C:/pastas/Projeto')
    expect(tokens.get(token)).toBe('C:/pastas/Projeto')
  })

  it('duas chamadas de issue para o mesmo caminho geram tokens diferentes', () => {
    const tokens = new FolderTokens()
    const a = tokens.issue('C:/pastas/Projeto')
    const b = tokens.issue('C:/pastas/Projeto')
    expect(a).not.toBe(b)
    expect(tokens.get(a)).toBe('C:/pastas/Projeto')
    expect(tokens.get(b)).toBe('C:/pastas/Projeto')
  })
})

import { describe, expect, it } from 'vitest'
import { isDevServerUrl } from '../navigation'

describe('isDevServerUrl', () => {
  it('aceita o servidor do Vite, com qualquer caminho', () => {
    expect(isDevServerUrl('http://localhost:5173')).toBe(true)
    expect(isDevServerUrl('http://localhost:5173/#/projetos')).toBe(true)
  })

  it('recusa o que só começa com o mesmo texto', () => {
    expect(isDevServerUrl('http://localhost:5173.evil.example/')).toBe(false)
    expect(isDevServerUrl('http://localhost:51730/')).toBe(false)
    expect(isDevServerUrl('http://localhost:5173@evil.example/')).toBe(false)
  })

  it('recusa outro esquema, outra porta e texto que nem é URL', () => {
    expect(isDevServerUrl('https://localhost:5173/')).toBe(false)
    expect(isDevServerUrl('http://localhost:5174/')).toBe(false)
    expect(isDevServerUrl('isso nao e url')).toBe(false)
  })
})

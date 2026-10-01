import { describe, expect, it } from 'vitest'
import { ipcErrorMessage } from '../ipcError'

describe('ipcErrorMessage', () => {
  it('tira o prefixo que o Electron põe nas rejeições de invoke', () => {
    const err = new Error("Error invoking remote method 'ragx:enqueueJob': Error: pedido recusado: fila cheia")
    expect(ipcErrorMessage(err)).toBe('pedido recusado: fila cheia')
  })

  it('tira o prefixo mesmo sem o "Error:" interno', () => {
    expect(ipcErrorMessage(new Error("Error invoking remote method 'ragx:x': só o motivo"))).toBe('só o motivo')
  })

  it('mensagem sem prefixo passa intacta', () => {
    expect(ipcErrorMessage(new Error('fila cheia'))).toBe('fila cheia')
  })

  it('valor que não é Error vira texto; vazio vira erro desconhecido', () => {
    expect(ipcErrorMessage('quebrou')).toBe('quebrou')
    expect(ipcErrorMessage(42)).toBe('42')
    expect(ipcErrorMessage(new Error(''))).toBe('erro desconhecido')
  })
})

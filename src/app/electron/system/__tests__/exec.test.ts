import { describe, expect, it } from 'vitest'
import { execFileText } from '../exec'

describe('execFileText', () => {
  it('nunca rejeita, mesmo quando execFile lança de forma síncrona', async () => {
    // Byte nulo em `file` faz `execFile` lançar ERR_INVALID_ARG_VALUE de
    // forma síncrona, antes de qualquer callback - sem o try/catch interno
    // isso vira rejeição da Promise, quebrando o contrato "nunca rejeita".
    await expect(execFileText('ragx\u0000bad', ['x'])).resolves.toEqual(
      expect.objectContaining({ code: -1 }),
    )
  })
})

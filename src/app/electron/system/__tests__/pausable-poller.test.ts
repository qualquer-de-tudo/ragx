import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPausablePoller } from '../pausable-poller'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const flush = async (): Promise<void> => {
  await Promise.resolve()
  await Promise.resolve()
}

describe('createPausablePoller', () => {
  it('executa a cada intervalo, a primeira depois de `intervalMs` (como o setInterval)', async () => {
    const run = vi.fn(async () => undefined)
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    expect(run).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(5000)
    expect(run).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(run).toHaveBeenCalledTimes(2)
    p.stop()
  })

  it('inativo não executa nada', async () => {
    const run = vi.fn()
    const p = createPausablePoller({ intervalMs: 1000, run })
    p.start()
    p.setActive(false)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(run).not.toHaveBeenCalled()
    p.stop()
  })

  it('ao ativar, executa na hora se passou o intervalo; senão espera só o que falta', async () => {
    const run = vi.fn(async () => undefined)
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    await vi.advanceTimersByTimeAsync(5000) // 1ª execução
    p.setActive(false)
    await vi.advanceTimersByTimeAsync(20_000)
    p.setActive(true) // a última execução tem 20 s: já passou
    await vi.advanceTimersByTimeAsync(0)
    expect(run).toHaveBeenCalledTimes(2)

    // pausa curta: volta antes de o intervalo vencer, espera o que falta
    await vi.advanceTimersByTimeAsync(1000) // 1 s depois da execução
    p.setActive(false)
    await vi.advanceTimersByTimeAsync(1000)
    p.setActive(true)
    await vi.advanceTimersByTimeAsync(2999)
    expect(run).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(run).toHaveBeenCalledTimes(3)
    p.stop()
  })

  it('não empilha: uma execução lenta adia a próxima para DEPOIS que ela termina', async () => {
    let finish: () => void = () => {}
    let started = 0
    const run = vi.fn(() => {
      started += 1
      return new Promise<void>((resolve) => (finish = resolve))
    })
    const p = createPausablePoller({ intervalMs: 1000, run })
    p.start()
    await vi.advanceTimersByTimeAsync(1000)
    expect(started).toBe(1)
    await vi.advanceTimersByTimeAsync(10_000) // muito mais que o intervalo, com a 1ª ainda rodando
    expect(started).toBe(1)
    finish()
    await flush()
    await vi.advanceTimersByTimeAsync(1000)
    expect(started).toBe(2)
    p.stop()
  })

  it('pausar no meio de uma execução: ela termina, mas não reagenda', async () => {
    let finish: () => void = () => {}
    const run = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)))
    const p = createPausablePoller({ intervalMs: 1000, run })
    p.start()
    await vi.advanceTimersByTimeAsync(1000)
    p.setActive(false)
    finish()
    await flush()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(run).toHaveBeenCalledTimes(1)
    p.stop()
  })

  it('stop() cancela o que estava agendado e start() de novo não duplica', async () => {
    const run = vi.fn(async () => undefined)
    const p = createPausablePoller({ intervalMs: 1000, run })
    p.start()
    p.start()
    p.stop()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(run).not.toHaveBeenCalled()
  })

  it('erro em `run` (lançado ou rejeitado) vai para `onError` e não derruba o poller', async () => {
    const onError = vi.fn()
    let n = 0
    const run = vi.fn(async () => {
      n += 1
      if (n === 1) throw new Error('rejeitou')
      if (n === 2) throw new Error('lançou')
    })
    const p = createPausablePoller({ intervalMs: 1000, run, onError })
    p.start()
    await vi.advanceTimersByTimeAsync(3000)
    expect(run).toHaveBeenCalledTimes(3)
    expect(onError).toHaveBeenCalledTimes(2)
    p.stop()
  })

  it('runNow executa já, uma só vez por execução em andamento, e só ativo', async () => {
    let finish: () => void = () => {}
    const run = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)))
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    p.runNow()
    p.runNow() // já em andamento: ignorado
    expect(run).toHaveBeenCalledTimes(1)
    finish()
    await flush()
    p.setActive(false)
    p.runNow() // inativo: ignorado
    expect(run).toHaveBeenCalledTimes(1)
    p.stop()
  })
})

describe('intervalo de fundo (RAGX-0191)', () => {
  it('sem intervalo de fundo (padrão) inativo continua parado por completo', async () => {
    const run = vi.fn()
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    p.setActive(false)
    await vi.advanceTimersByTimeAsync(10 * 60_000)
    expect(run).not.toHaveBeenCalled()
    p.stop()
  })

  it('com intervalo de fundo, inativo roda no máximo uma vez por esse intervalo', async () => {
    const run = vi.fn(async () => undefined)
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    p.setBackgroundInterval(60_000)
    p.setActive(false)
    await vi.advanceTimersByTimeAsync(5 * 60_000)
    expect(run.mock.calls.length).toBeGreaterThanOrEqual(4)
    expect(run.mock.calls.length).toBeLessThanOrEqual(5)
    p.stop()
  })

  it('ligar o fundo com o poller já inativo agenda; desligar (null) volta à pausa total', async () => {
    const run = vi.fn(async () => undefined)
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    p.setActive(false)
    await vi.advanceTimersByTimeAsync(120_000)
    expect(run).not.toHaveBeenCalled()
    p.setBackgroundInterval(30_000)
    await vi.advanceTimersByTimeAsync(31_000)
    // a última execução foi há mais que o intervalo de fundo: roda na hora e de novo a cada 30 s
    const comFundo = run.mock.calls.length
    expect(comFundo).toBeGreaterThanOrEqual(1)
    expect(comFundo).toBeLessThanOrEqual(2)
    p.setBackgroundInterval(null)
    await vi.advanceTimersByTimeAsync(10 * 60_000)
    expect(run).toHaveBeenCalledTimes(comFundo)
    p.stop()
  })

  it('ativo, o intervalo de fundo não muda nada (continua o normal)', async () => {
    const run = vi.fn(async () => undefined)
    const p = createPausablePoller({ intervalMs: 5000, run })
    p.start()
    p.setBackgroundInterval(60_000)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(run).toHaveBeenCalledTimes(4)
    p.stop()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { createCoalescedRun } from '../coalesced-run'

function controllable() {
  const releases: Array<(v: number) => void> = []
  const rejects: Array<(e: Error) => void> = []
  let n = 0
  const task = vi.fn(
    () =>
      new Promise<number>((resolve, reject) => {
        const id = ++n
        releases.push(() => resolve(id))
        rejects.push(reject)
      }),
  )
  return {
    task,
    release: (i: number) => releases[i](0),
    fail: (i: number) => rejects[i](new Error(`falhou ${i}`)),
  }
}

async function flush(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

describe('createCoalescedRun', () => {
  it('join: chamadas simultâneas recebem a mesma execução', async () => {
    const c = controllable()
    const r = createCoalescedRun(c.task)
    const a = r.join()
    const b = r.join()
    expect(a).toBe(b)
    c.release(0)
    expect(await a).toBe(1)
    expect(c.task).toHaveBeenCalledOnce()
  })

  it('fresh sem nada em andamento: roda na hora', async () => {
    const c = controllable()
    const r = createCoalescedRun(c.task)
    const p = r.fresh()
    expect(c.task).toHaveBeenCalledOnce()
    c.release(0)
    expect(await p).toBe(1)
  })

  it('fresh com execução em andamento: exatamente mais uma, que começa depois dela', async () => {
    const c = controllable()
    const r = createCoalescedRun(c.task)
    const antiga = r.join() // polling de 30 s em andamento
    const depois1 = r.fresh() // tarefa terminou no meio
    const depois2 = r.fresh() // outra tarefa terminou no meio da mesma checagem
    expect(depois1).toBe(depois2)
    expect(c.task).toHaveBeenCalledOnce()

    c.release(0)
    expect(await antiga).toBe(1)
    await flush()
    expect(c.task).toHaveBeenCalledTimes(2) // a extra começou só depois da antiga

    c.release(1)
    expect(await depois1).toBe(2)
    await flush()
    expect(c.task).toHaveBeenCalledTimes(2) // nunca vira laço
  })

  it('join chamado enquanto a extra roda recebe a extra', async () => {
    const c = controllable()
    const r = createCoalescedRun(c.task)
    void r.join()
    const extra = r.fresh()
    c.release(0)
    await flush()
    const juntou = r.join()
    c.release(1)
    expect(await juntou).toBe(2)
    expect(await extra).toBe(2)
    expect(c.task).toHaveBeenCalledTimes(2)
  })

  it('a extra roda mesmo se a execução antiga falhar', async () => {
    const c = controllable()
    const r = createCoalescedRun(c.task)
    const antiga = r.join()
    const extra = r.fresh()
    c.fail(0)
    await expect(antiga).rejects.toThrow('falhou 0')
    await flush()
    c.release(1)
    expect(await extra).toBe(2)
  })

  it('uma execução que falha não trava as seguintes', async () => {
    const c = controllable()
    const r = createCoalescedRun(c.task)
    const a = r.join()
    c.fail(0)
    await expect(a).rejects.toThrow()
    const b = r.join()
    c.release(1)
    expect(await b).toBe(2)
  })

  it('tarefa que lança de forma síncrona vira rejeição', async () => {
    const r = createCoalescedRun<number>(() => {
      throw new Error('sync')
    })
    await expect(r.join()).rejects.toThrow('sync')
    await expect(r.fresh()).rejects.toThrow('sync')
  })
})

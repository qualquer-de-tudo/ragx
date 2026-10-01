import { describe, expect, it } from 'vitest'
import { STALE_GRACE_MS, StaleNotifier } from '../stale-notifier'
import type { ProjectState } from '../project-state'

const obs = (state: ProjectState, id = 'p1') => [{ id, name: id.toUpperCase(), state }]
const T = 1_000_000

/** O primeiro snapshot semeia (sem notificar o que já estava defasado): começa sempre com um `ok`. */
function started(n = new StaleNotifier()) {
  n.observe(obs('ok'), T)
  return n
}

describe('StaleNotifier', () => {
  it('defasado por menos de 120 s não notifica', () => {
    const n = started()
    expect(n.observe(obs('stale'), T + 1000)).toEqual([])
    expect(n.observe(obs('stale'), T + 1000 + STALE_GRACE_MS - 1)).toEqual([])
  })

  it('passou de 120 s notifica UMA vez, com o tempo defasado; mais snapshots no episódio não repetem', () => {
    const n = started()
    n.observe(obs('stale'), T + 1000)
    const out = n.observe(obs('stale'), T + 1000 + STALE_GRACE_MS)
    expect(out).toEqual([{ projectId: 'p1', name: 'P1', staleForMs: STALE_GRACE_MS }])
    expect(n.observe(obs('stale'), T + 1000 + STALE_GRACE_MS + 5000)).toEqual([])
    expect(n.observe(obs('stale'), T + 1000 + 10 * STALE_GRACE_MS)).toEqual([])
  })

  it('voltar a ok e defasar de novo abre outro episódio e notifica de novo', () => {
    const n = started()
    n.observe(obs('stale'), T + 1000)
    expect(n.observe(obs('stale'), T + 1000 + STALE_GRACE_MS)).toHaveLength(1)
    n.observe(obs('ok'), T + 200_000)
    n.observe(obs('stale'), T + 210_000)
    expect(n.observe(obs('stale'), T + 210_000 + STALE_GRACE_MS)).toHaveLength(1)
  })

  it('indexing no meio não zera o relógio nem abre episódio novo', () => {
    const n = started()
    n.observe(obs('stale'), T + 1000)
    n.observe(obs('indexing'), T + 60_000)
    expect(n.observe(obs('stale'), T + 1000 + STALE_GRACE_MS)).toHaveLength(1) // o relógio é o de T+1000
    n.observe(obs('indexing'), T + 500_000)
    expect(n.observe(obs('stale'), T + 600_000)).toEqual([]) // ainda o mesmo episódio, já avisado
  })

  it('indexing não abre episódio sozinho', () => {
    const n = started()
    n.observe(obs('indexing'), T + 1000)
    expect(n.observe(obs('indexing'), T + 1000 + 10 * STALE_GRACE_MS)).toEqual([])
  })

  it('embeddings, error e missing fecham o episódio (não são defasagem)', () => {
    for (const other of ['embeddings', 'error', 'missing', 'no-hooks', 'ok'] as const) {
      const n = started()
      n.observe(obs('stale'), T + 1000)
      n.observe(obs(other), T + 50_000)
      n.observe(obs('stale'), T + 60_000)
      expect(n.observe(obs('stale'), T + 60_000 + STALE_GRACE_MS - 1)).toEqual([])
    }
  })

  it('episódio já aberto no primeiro snapshot do processo é semeado sem notificar', () => {
    const n = new StaleNotifier()
    n.observe(obs('stale'), T)
    expect(n.observe(obs('stale'), T + 10 * STALE_GRACE_MS)).toEqual([])
    n.observe(obs('ok'), T + 11 * STALE_GRACE_MS)
    n.observe(obs('stale'), T + 12 * STALE_GRACE_MS)
    expect(n.observe(obs('stale'), T + 12 * STALE_GRACE_MS + STALE_GRACE_MS)).toHaveLength(1) // o seguinte conta
  })

  it('projetos são independentes, e um removido some', () => {
    const n = started()
    const both = (a: ProjectState, b: ProjectState) => [...obs(a, 'p1'), ...obs(b, 'p2')]
    n.observe(both('stale', 'ok'), T + 1000)
    const out = n.observe(both('stale', 'stale'), T + 1000 + STALE_GRACE_MS)
    expect(out.map((o) => o.projectId)).toEqual(['p1'])
    n.observe(obs('ok', 'p1'), T + 300_000) // p2 saiu do snapshot
    n.observe(both('ok', 'stale'), T + 310_000) // p2 volta como episódio novo
    expect(n.observe(both('ok', 'stale'), T + 310_000 + STALE_GRACE_MS).map((o) => o.projectId)).toEqual(['p2'])
  })

  it('reset (opção desligada) semeia de novo ao ligar', () => {
    const n = started()
    n.reset()
    n.observe(obs('stale'), T + 1000)
    expect(n.observe(obs('stale'), T + 1000 + 10 * STALE_GRACE_MS)).toEqual([])
  })
})

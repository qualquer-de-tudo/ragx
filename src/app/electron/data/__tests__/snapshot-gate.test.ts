import { describe, expect, it } from 'vitest'
import { createSnapshotGate } from '../snapshot-gate'
import type { Snapshot } from '../../../src/types/ragx-bridge'

const snap = (over: Partial<Snapshot> = {}): Snapshot => ({ projects: [], generatedAt: '2026-10-01T12:00:00Z', ...over })

describe('createSnapshotGate', () => {
  it('o primeiro snapshot sempre sai', () => {
    expect(createSnapshotGate().shouldSend(snap())).toBe(true)
  })

  it('só generatedAt diferente não sai', () => {
    const gate = createSnapshotGate()
    expect(gate.shouldSend(snap())).toBe(true)
    expect(gate.shouldSend(snap({ generatedAt: '2026-10-01T12:00:05Z' }))).toBe(false)
  })

  it('conteúdo diferente sai, e o seguinte igual a ele não', () => {
    const gate = createSnapshotGate()
    gate.shouldSend(snap())
    expect(gate.shouldSend(snap({ connectionsHealth: 'warn' }))).toBe(true)
    expect(gate.shouldSend(snap({ connectionsHealth: 'warn', generatedAt: 'x' }))).toBe(false)
  })

  it('reset (janela nova) faz o próximo sair mesmo igual', () => {
    const gate = createSnapshotGate()
    gate.shouldSend(snap())
    gate.reset()
    expect(gate.shouldSend(snap())).toBe(true)
  })
})

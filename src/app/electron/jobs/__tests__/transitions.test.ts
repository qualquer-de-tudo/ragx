import { describe, expect, it } from 'vitest'
import { CONNECTION_JOB_KINDS, justFinishedJobs } from '../transitions'
import type { JobView } from '../../../src/types/ragx-bridge'

function view(id: string, kind: JobView['kind'], state: JobView['state']): JobView {
  return {
    id,
    kind,
    label: id,
    projectId: null,
    model: null,
    state,
    step: 1,
    steps: 1,
    phase: null,
    done: null,
    total: null,
    etaSeconds: null,
    ratePerSecond: null,
    note: null,
    error: null,
    logTail: [],
    queuedAt: '2026-09-23T10:00:00Z',
    startedAt: null,
    finishedAt: null,
  }
}

describe('justFinishedJobs', () => {
  it('só as que saíram de queued/running para um estado final', () => {
    const prev = new Map<string, JobView['state']>([
      ['a', 'running'],
      ['b', 'running'],
      ['c', 'done'],
    ])
    const now = [view('a', 'mcp-register', 'failed'), view('b', 'update', 'running'), view('c', 'update', 'done'), view('d', 'ollama-pull', 'done')]
    expect(justFinishedJobs(prev, now).map((j) => j.id)).toEqual(['a'])
  })
})

describe('CONNECTION_JOB_KINDS', () => {
  it('são as correções de um clique da tela Conexões', () => {
    expect([...CONNECTION_JOB_KINDS].sort()).toEqual(['mcp-register', 'ollama-pull', 'ollama-start'])
  })
})

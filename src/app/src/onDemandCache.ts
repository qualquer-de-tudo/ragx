import type { SecurityScanResult, TrialResult } from './types/ragx-bridge'

export interface Cached<T> {
  result: T
  at: string
}

interface Entry {
  trial?: Cached<TrialResult>
  scan?: Cached<SecurityScanResult>
}

// Trial e scan levam segundos: trocar de projeto e voltar não deve obrigar a rodar de novo.
const cache = new Map<string, Entry>()

export function readCache(projectId: string): Entry {
  return cache.get(projectId) ?? {}
}

export function writeTrial(projectId: string, result: TrialResult): Cached<TrialResult> {
  const cached = { result, at: new Date().toISOString() }
  cache.set(projectId, { ...readCache(projectId), trial: cached })
  return cached
}

export function writeScan(projectId: string, result: SecurityScanResult): Cached<SecurityScanResult> {
  const cached = { result, at: new Date().toISOString() }
  cache.set(projectId, { ...readCache(projectId), scan: cached })
  return cached
}

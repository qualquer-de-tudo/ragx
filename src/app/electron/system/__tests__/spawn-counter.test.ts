import { beforeEach, describe, expect, it } from 'vitest'
import {
  addSpawnDuration,
  countSpawn,
  diffSpawns,
  executableName,
  resetSpawnCounter,
  snapshot,
} from '../spawn-counter'

beforeEach(() => resetSpawnCounter())

describe('executableName', () => {
  it('agrupa pelo nome do executável, com caminho completo e .exe', () => {
    expect(executableName('git')).toBe('git')
    expect(executableName('C:\\Program Files\\Git\\cmd\\git.exe')).toBe('git')
    expect(executableName('/usr/bin/docker')).toBe('docker')
    expect(executableName('C:\\Users\\x\\.local\\bin\\ragx.exe')).toBe('ragx')
    expect(executableName('C:\\Windows\\System32\\TASKLIST.EXE')).toBe('tasklist')
    expect(executableName('powershell.exe')).toBe('powershell')
  })

  it('qualquer outro executável vira `outro`', () => {
    expect(executableName('C:\\tools\\algo-raro.exe')).toBe('outro')
    expect(executableName('')).toBe('outro')
  })
})

describe('countSpawn', () => {
  it('conta por executável e soma a duração', () => {
    countSpawn('git', 40)
    countSpawn('C:\\Git\\git.exe', 60)
    countSpawn('docker')
    expect(snapshot()).toEqual({ git: { count: 2, ms: 100 }, docker: { count: 1, ms: 0 } })
  })

  it('addSpawnDuration soma só o tempo, sem contar outro processo', () => {
    countSpawn('ragx')
    addSpawnDuration('ragx', 250)
    expect(snapshot().ragx).toEqual({ count: 1, ms: 250 })
  })

  it('duração negativa vira zero e nunca lança', () => {
    expect(() => countSpawn('git', -5)).not.toThrow()
    expect(snapshot().git.ms).toBe(0)
  })

  it('a fotografia é uma cópia: contar depois não a altera', () => {
    countSpawn('git')
    const antes = snapshot()
    countSpawn('git')
    expect(antes.git.count).toBe(1)
  })
})

describe('diffSpawns', () => {
  it('devolve só o que mudou entre duas fotografias', () => {
    countSpawn('git', 10)
    const a = snapshot()
    countSpawn('git', 30)
    countSpawn('docker', 5)
    const b = snapshot()
    expect(diffSpawns(a, b)).toEqual({ git: { count: 1, ms: 30 }, docker: { count: 1, ms: 5 } })
    expect(diffSpawns(b, b)).toEqual({})
  })
})

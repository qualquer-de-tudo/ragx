import { describe, expect, it, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { readTelemetry } from '../telemetry'

describe('readTelemetry', () => {
  let projectPath: string

  beforeEach(() => {
    projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-telemetry-test-'))
  })

  it('devolve zerado quando mcp.jsonl nao existe', () => {
    const result = readTelemetry(projectPath, 24)
    expect(result).toEqual({ callsByTool: [], totalCalls: 0, tokensDelivered: 0 })
  })

  it('agrega chamadas por ferramenta e soma tokens_delivered', () => {
    const logDir = path.join(projectPath, '.ragx', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const now = new Date().toISOString()
    const lines = [
      { ts: now, tool: 'search_hybrid', ms: 10, project: 't' },
      { ts: now, tool: 'search_hybrid', ms: 12, project: 't' },
      { ts: now, tool: 'build_context', ms: 30, project: 't', tokens_delivered: 500 },
      { ts: now, tool: 'build_context', ms: 28, project: 't', tokens_delivered: 300 },
    ]
    fs.writeFileSync(
      path.join(logDir, 'mcp.jsonl'),
      lines.map((l) => JSON.stringify(l)).join('\n') + '\n',
      'utf-8',
    )

    const result = readTelemetry(projectPath, 24)
    expect(result.totalCalls).toBe(4)
    expect(result.tokensDelivered).toBe(800)
    expect(result.callsByTool).toEqual(
      expect.arrayContaining([
        { tool: 'search_hybrid', count: 2 },
        { tool: 'build_context', count: 2 },
      ]),
    )
  })

  it('ignora linhas mais antigas que sinceHours', () => {
    const logDir = path.join(projectPath, '.ragx', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const old = new Date(Date.now() - 48 * 3600 * 1000).toISOString()
    const recent = new Date().toISOString()
    const lines = [
      { ts: old, tool: 'search_hybrid', ms: 10, project: 't' },
      { ts: recent, tool: 'search_hybrid', ms: 10, project: 't' },
    ]
    fs.writeFileSync(
      path.join(logDir, 'mcp.jsonl'),
      lines.map((l) => JSON.stringify(l)).join('\n') + '\n',
      'utf-8',
    )

    const result = readTelemetry(projectPath, 24)
    expect(result.totalCalls).toBe(1)
  })
})

import { describe, expect, it, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { emptySavings, readTelemetry, SAVINGS_DAYS } from '../telemetry'

describe('readTelemetry', () => {
  let projectPath: string

  beforeEach(() => {
    projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-telemetry-test-'))
  })

  it('devolve zerado quando mcp.jsonl nao existe', () => {
    const result = readTelemetry(projectPath, 24)
    expect(result).toMatchObject({ callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null })
    expect(result.savings?.days).toHaveLength(SAVINGS_DAYS)
    expect(result.savings?.calls).toBe(0)
  })

  it('lastCallAt e null sem log', () => {
    const result = readTelemetry(projectPath, 24)
    expect(result.lastCallAt).toBeNull()
  })

  it('lastCallAt e o maior ts mesmo fora da janela de sinceHours', () => {
    const logDir = path.join(projectPath, '.ragx', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const older = new Date(Date.now() - 72 * 3600 * 1000).toISOString()
    const lessOld = new Date(Date.now() - 48 * 3600 * 1000).toISOString()
    const lines = [
      { ts: older, tool: 'search_hybrid', ms: 10, project: 't' },
      { ts: lessOld, tool: 'search_hybrid', ms: 10, project: 't' },
    ]
    fs.writeFileSync(
      path.join(logDir, 'mcp.jsonl'),
      lines.map((l) => JSON.stringify(l)).join('\n') + '\n',
      'utf-8',
    )

    const result = readTelemetry(projectPath, 24)
    // as duas linhas estao fora da janela de 24h - nao entram na agregacao...
    expect(result.totalCalls).toBe(0)
    // ...mas lastCallAt reflete a mais recente das duas mesmo assim.
    expect(result.lastCallAt).toBe(lessOld)
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

  describe('savings (gráfico de economia)', () => {
    function write(lines: object[]) {
      const logDir = path.join(projectPath, '.ragx', 'logs')
      fs.mkdirSync(logDir, { recursive: true })
      fs.writeFileSync(path.join(logDir, 'mcp.jsonl'), lines.map((l) => JSON.stringify(l)).join('\n') + '\n', 'utf-8')
    }
    const ago = (h: number) => new Date(Date.now() - h * 3600 * 1000).toISOString()

    it('soma baseline e entregue por dia, só de build_context com as duas medidas', () => {
      write([
        { ts: ago(0), tool: 'build_context', ms: 1, project: 't', tokens_delivered: 1000, baseline_tokens: 9000 },
        { ts: ago(0), tool: 'build_context', ms: 1, project: 't', tokens_delivered: 500, baseline_tokens: 1000 },
        // linha antiga, sem baseline: fora (seria "100% de economia")
        { ts: ago(0), tool: 'build_context', ms: 1, project: 't', tokens_delivered: 700 },
        { ts: ago(0), tool: 'search_hybrid', ms: 1, project: 't', baseline_tokens: 99 },
        // fora da janela de 14 dias
        { ts: ago(24 * 30), tool: 'build_context', ms: 1, project: 't', tokens_delivered: 1, baseline_tokens: 2 },
      ])
      const s = readTelemetry(projectPath, 24).savings!
      expect(s.calls).toBe(2)
      expect(s.baseline).toBe(10000)
      expect(s.delivered).toBe(1500)
      const today = s.days[s.days.length - 1]
      expect(today).toMatchObject({ baseline: 10000, delivered: 1500, calls: 2 })
    })

    it('a série tem um dia por posição, do mais antigo a hoje, sem buracos', () => {
      const s = emptySavings(new Date(2026, 2, 3, 9).getTime(), 5)
      expect(s.days.map((d) => d.date)).toEqual(['2026-02-27', '2026-02-28', '2026-03-01', '2026-03-02', '2026-03-03'])
    })
  })
})

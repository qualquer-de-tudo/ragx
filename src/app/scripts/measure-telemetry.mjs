#!/usr/bin/env node
/**
 * Mede o custo da leitura da telemetria do painel (RAGX-0174): a leitura COMPLETA que existia
 * (`readTelemetryFull`, relê o `mcp.jsonl` inteiro) contra a incremental (`createTelemetryTail`), com 12
 * projetos e um `mcp.jsonl` sintético de 1, 10 e 50 MB (linhas no formato do servidor MCP).
 *
 *   node scripts/measure-telemetry.mjs [--sizes 1,10,50] [--projects 12]
 *
 * Pré-requisito: `npm run build:electron:ts`. Os arquivos ficam em %TEMP% e são apagados no fim.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const { readTelemetryFull, createTelemetryTail } = require(path.join(root, 'dist-electron', 'data', 'telemetry.js'))

const args = process.argv.slice(2)
const opt = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback)
const sizes = opt('--sizes', '1,10,50').split(',').map(Number)
const projects = Number(opt('--projects', '12'))

function line(i) {
  const tools = ['search_hybrid', 'build_context', 'get_chunk', 'get_dictionary', 'refresh']
  const tool = tools[i % tools.length]
  const entry = {
    v: 2, ts: new Date(Date.now() - (i % (14 * 24 * 3600)) * 1000).toISOString(), tool, ms: 12.5, project: 'p',
    proc: 'abcd1234', ok: true, resp_chars: 2400, resp_tokens: 700, client: 'claude-code', profile: 'padrão', session: 'deadbeef',
  }
  if (tool === 'build_context') Object.assign(entry, { tokens_delivered: 1800, baseline_tokens: 9000 })
  return JSON.stringify(entry) + '\n'
}

function makeLog(file, mb) {
  const fd = fs.openSync(file, 'w')
  let written = 0
  let i = 0
  const target = mb * 1024 * 1024
  const chunk = []
  while (written < target) {
    const l = line(i++)
    chunk.push(l)
    written += l.length
    if (chunk.length === 5000) {
      fs.writeSync(fd, chunk.join(''))
      chunk.length = 0
    }
  }
  if (chunk.length) fs.writeSync(fd, chunk.join(''))
  fs.closeSync(fd)
  return i
}

const ms = (t0) => Number(process.hrtime.bigint() - t0) / 1e6

console.log(`| mcp.jsonl | linhas | leitura completa, ${projects} projetos (ms) | incremental, 1ª leitura (ms) | incremental, estado estável por ciclo (ms) | ganho no estado estável |`)
console.log('|---|---|---|---|---|---|')
for (const mb of sizes) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-tel-'))
  const dirs = []
  const first = path.join(base, 'p00', '.ragx', 'logs', 'mcp.jsonl')
  fs.mkdirSync(path.dirname(first), { recursive: true })
  const lines = makeLog(first, mb)
  dirs.push(path.join(base, 'p00'))
  for (let p = 1; p < projects; p++) {
    const d = path.join(base, `p${String(p).padStart(2, '0')}`)
    fs.mkdirSync(path.join(d, '.ragx', 'logs'), { recursive: true })
    fs.linkSync(first, path.join(d, '.ragx', 'logs', 'mcp.jsonl')) // o mesmo arquivo: não gasta disco
    dirs.push(d)
  }

  // leitura completa (a que o painel fazia a cada 5 s)
  let t0 = process.hrtime.bigint()
  for (const d of dirs) readTelemetryFull(d, 24)
  const full = ms(t0)

  const tail = createTelemetryTail()
  t0 = process.hrtime.bigint()
  for (const d of dirs) tail.read(d, 24)
  const firstRead = ms(t0)

  const cycles = 200
  t0 = process.hrtime.bigint()
  for (let c = 0; c < cycles; c++) for (const d of dirs) tail.read(d, 24)
  const steady = ms(t0) / cycles

  console.log(`| ${mb} MB | ${lines} | ${full.toFixed(0)} | ${firstRead.toFixed(0)} | ${steady.toFixed(3)} (${(steady / projects).toFixed(4)} por projeto) | ${(full / steady).toFixed(0)}x |`)
  fs.rmSync(base, { recursive: true, force: true })
}

#!/usr/bin/env node
/**
 * Mede o consumo do painel em execução (RAGX-0177): RAM, CPU e filhos criados por minuto, com a janela
 * visível, minimizada e oculta.
 *
 *   node scripts/measure-runtime.mjs --plan visible:5,minimized:5,hidden:5 --label baseline-1.0.0-beta.5 \
 *        [--exe <caminho>] [--projects fixture12|real] [--warmup 1]
 *
 * Sobe o Electron com `--user-data-dir` temporário e `RAGX_PANEL_METRICS*`, espera ele sair, lê o JSONL (em
 * %TEMP%, não versionado) e ACRESCENTA uma seção a `docs/medicao-runtime.md`. Não muda nada no painel além
 * de ligar o amostrador opt-in (ver `electron/system/runtime-metrics.ts`).
 *
 * Pré-requisito: `npm run build && npm run build:electron:ts` (casca de produção em `dist/` e `dist-electron/`).
 */
import { execFileSync, spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function parseArgs(argv) {
  const out = { plan: 'visible:5,minimized:5,hidden:5', label: 'medicao', exe: null, projects: 'fixture12', warmup: 1 }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    const next = () => argv[++i]
    if (a === '--plan') out.plan = next()
    else if (a === '--label') out.label = next()
    else if (a === '--exe') out.exe = next()
    else if (a === '--projects') out.projects = next()
    else if (a === '--warmup') out.warmup = Number(next())
    else throw new Error(`argumento desconhecido: ${a}`)
  }
  if (!['fixture12', 'real'].includes(out.projects)) throw new Error('--projects é fixture12 ou real')
  return out
}

/** 12 repositórios `git init` com `.ragx/status.json` e um hub de 12 projetos, tudo em pasta temporária. */
function makeFixture(base) {
  const home = path.join(base, 'home')
  const hub = path.join(home, '.ragx', 'hub')
  fs.mkdirSync(hub, { recursive: true })
  const projects = []
  for (let i = 1; i <= 12; i++) {
    const dir = path.join(base, 'projects', `projeto-${String(i).padStart(2, '0')}`)
    fs.mkdirSync(path.join(dir, '.ragx'), { recursive: true })
    fs.writeFileSync(path.join(dir, 'README.md'), `# projeto ${i}\n`)
    execFileSync('git', ['init', '-q'], { cwd: dir })
    execFileSync('git', ['-c', 'user.email=m@m', '-c', 'user.name=m', 'add', '.'], { cwd: dir })
    execFileSync('git', ['-c', 'user.email=m@m', '-c', 'user.name=m', 'commit', '-q', '-m', 'inicial'], { cwd: dir })
    const commit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: dir, encoding: 'utf-8' }).trim()
    fs.writeFileSync(
      path.join(dir, '.ragx', 'status.json'),
      JSON.stringify({
        schema_version: 1,
        written_at: new Date().toISOString(),
        project: { id: `p${i}`, name: `projeto-${i}`, root: dir },
        index: { finished_at: new Date().toISOString(), mode: 'incremental', source: 'cli', branch: 'main', commit, dirty: false },
        counts: { documents: 100 + i, chunks: 1000 + i, embeddings: 1000 + i, pending_embeddings: 0 },
        embedding: { provider: 'hashing', model: 'hashing:64' },
        hooks: { installed: true },
        running: null,
        pending: false,
        last_error: null,
      }),
    )
    projects.push({
      id: `p${i}`, name: `projeto-${i}`, path: dir, cloned: 1, embedding_model: 'hashing:64',
      visibility: 'workspace', status: 'indexed', chunks: 1000 + i, last_sync: new Date().toISOString(),
    })
  }
  fs.writeFileSync(path.join(hub, 'registry.json'), JSON.stringify({ schema_version: 1, projects }))
  return { home, count: projects.length }
}

function electronCommand(exe) {
  if (exe) return exe
  return require('electron') // o caminho do binário do pacote `electron`
}

function section({ args, env, samples, summaries, markdownTable, electronVersion, panelVersion, projectCount, minutes }) {
  const cpus = os.cpus()
  const lines = [
    `## ${args.label}`,
    '',
    `- Data: ${new Date().toISOString()}`,
    `- Máquina: ${os.type()} ${os.release()} (${os.platform()} ${os.arch()}), ${cpus.length} núcleos lógicos, ${cpus[0]?.model?.trim() ?? '?'}, ${(os.totalmem() / 1024 ** 3).toFixed(1)} GB de RAM`,
    `- Painel ${panelVersion}, Electron ${electronVersion}${args.exe ? `, executável ${args.exe}` : ' (não empacotado: `electron dist-electron/main.js`, casca de produção)'}`,
    `- Projetos no hub: ${projectCount} (${args.projects === 'real' ? 'hub real da máquina, somente leitura' : 'fixture: 12 repositórios `git init` em pasta temporária'})`,
    `- Plano: \`${args.plan}\` (${minutes} min); amostra a cada 5 s; a 1ª amostra de cada execução é descartada (\`warmup\`)`,
    `- Amostras: ${samples.length} (JSONL em %TEMP%, não versionado)`,
    '- Convenção de CPU: `percentCPUUsage` do `app.getAppMetrics()`, medido desde a chamada anterior; **por núcleo** (pode passar de 100), somado entre os processos do painel',
    '',
    markdownTable,
    '',
  ]
  for (const s of summaries) {
    const spawns = Object.entries(s.spawnsPerMinute).map(([k, v]) => `${k} ${v}`).join(', ') || 'nenhum'
    const ms = Object.entries(s.spawnMsPerMinute).map(([k, v]) => `${k} ${Math.round(v)}`).join(', ') || 'nenhum'
    const cpu = Object.entries(s.cpuByType).map(([k, v]) => `${k} ${v.mean}/${v.p95}`).join(', ')
    lines.push(`- **${s.state}** (${s.samples} amostras, ${s.seconds} s): filhos/min: ${spawns}; ms de filhos/min: ${ms}; CPU média/p95 por tipo: ${cpu}; custo médio do amostrador: ${s.sampleCostMsMean ?? '-'} ms`)
  }
  lines.push('')
  return lines.join('\n')
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const summaryMod = require(path.join(root, 'dist-electron', 'system', 'runtime-summary.js'))
  const steps = summaryMod.parsePlan(args.plan)
  const minutes = steps.reduce((a, s) => a + s.minutes, 0)
  if (!fs.existsSync(path.join(root, 'dist-electron', 'main.js')) || !fs.existsSync(path.join(root, 'dist', 'index.html'))) {
    throw new Error('faltam `dist/` e `dist-electron/`: rode `npm run build && npm run build:electron:ts` antes')
  }

  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-measure-'))
  const metricsFile = path.join(base, 'metrics.jsonl')
  const env = { ...process.env, RAGX_PANEL_METRICS: metricsFile, RAGX_PANEL_METRICS_PLAN: args.plan }
  delete env.NODE_ENV
  delete env.ELECTRON_RUN_AS_NODE
  let projectCount = 12
  if (args.projects === 'fixture12') {
    const f = makeFixture(base)
    env.USERPROFILE = f.home
    env.HOME = f.home
    projectCount = f.count
  } else {
    try {
      projectCount = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.ragx', 'hub', 'registry.json'), 'utf-8')).projects.length
    } catch {
      projectCount = 0
    }
  }

  const command = electronCommand(args.exe)
  const argv = args.exe ? [] : [path.join(root, 'dist-electron', 'main.js')]
  argv.push(`--user-data-dir=${path.join(base, 'userdata')}`)
  console.log(`medindo ${minutes} min (${args.plan}) em ${base} ...`)
  const child = spawn(command, argv, { cwd: root, env, stdio: 'ignore' })
  const code = await new Promise((resolve) => child.on('exit', resolve))
  console.log(`o painel saiu com código ${code}`)

  if (!fs.existsSync(metricsFile)) throw new Error('o painel não gravou o JSONL de métricas')
  const samples = summaryMod.parseSamples(fs.readFileSync(metricsFile, 'utf-8'))
  const summaries = summaryMod.summarize(samples)
  const electronVersion = require('electron/package.json').version
  const panelVersion = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf-8')).version
  const text = section({
    args, env, samples, summaries, markdownTable: summaryMod.toMarkdownTable(summaries),
    electronVersion, panelVersion, projectCount, minutes,
  })
  const docs = path.join(root, 'docs')
  fs.mkdirSync(docs, { recursive: true })
  const file = path.join(docs, 'medicao-runtime.md')
  if (!fs.existsSync(file)) {
    fs.writeFileSync(file, '# Medição de consumo do painel\n\nSeções acrescentadas por `node scripts/measure-runtime.mjs` (RAGX-0177). Os JSONL brutos ficam em %TEMP% e não são versionados.\n\n')
  }
  fs.appendFileSync(file, `${text}\n`)
  console.log(`seção "${args.label}" acrescentada a ${file}`)
  console.log(summaryMod.toMarkdownTable(summaries))
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err)
  process.exit(1)
})

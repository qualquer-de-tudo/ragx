#!/usr/bin/env node
/**
 * Verificação visual do painel (RAGX-0181): sobe `vite preview` sobre `dist/`, abre o Edge (`playwright-core`, canal
 * `msedge`, sem baixar navegador) com um `window.ragx` simulado (`scripts/visual-fixtures/bridge.js`, ~12 projetos) e,
 * para cada tela e cada largura, lista o que estoura a janela.
 *
 *   npm run build && node scripts/visual-check.mjs [--widths 450,480,600,900,1280,3440] [--screens projetos-grade,...]
 *                                                  [--shots <pasta>] [--json]
 *
 * O que conta como estouro: elemento com `getBoundingClientRect().right > innerWidth + 1` fora de ancestral com
 * `overflow-x: auto|scroll|hidden|clip`, mais `scrollWidth > clientWidth` em `.shell`, `.shell-main`, `.topbar` e
 * `.content`. (`html` e `body` têm `overflow: hidden`: o estouro corta em vez de rolar, então `scrollWidth` do
 * documento não serve.) Em telas largas mede também se a topbar e o conteúdo compartilham as bordas.
 *
 * Sem o Edge (ou sem `dist/`), sai com 2 e diz por quê. Nunca roda no `npm test`.
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const args = process.argv.slice(2)
const opt = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback)
const widths = opt('--widths', '450,480,600,900,1280,3440').split(',').map(Number)
const only = opt('--screens', '')
  .split(',')
  .filter(Boolean)
const shotsDir = opt('--shots', null)
const asJson = args.includes('--json')
const PORT = Number(opt('--port', '4173'))
const HEIGHT = Number(opt('--height', '800'))

function fail(code, message) {
  console.error(`visual-check: ${message}`)
  process.exit(code)
}

if (!fs.existsSync(path.join(root, 'dist', 'index.html'))) fail(2, 'dist/index.html não existe; rode `npm run build` antes.')

let chromium
try {
  ;({ chromium } = await import('playwright-core'))
} catch {
  fail(2, 'playwright-core não está instalado (`npm install`).')
}

function waitFor(url, ms = 15000) {
  const until = Date.now() + ms
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(url, (res) => {
          res.resume()
          resolve()
        })
        .on('error', () => {
          if (Date.now() > until) reject(new Error(`servidor não subiu em ${url}`))
          else setTimeout(tick, 250)
        })
    }
    tick()
  })
}

const vite = spawn(process.execPath, [path.join(root, 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--port', String(PORT), '--strictPort'], {
  cwd: root,
  stdio: 'ignore',
})
const stop = () => {
  try {
    vite.kill()
  } catch {
    /* já saiu */
  }
}
process.on('exit', stop)

let browser
try {
  await waitFor(`http://localhost:${PORT}/`)
  try {
    // `--hide-scrollbars` (padrão do headless) esconde a barra de rolagem; sem ela a calha de 12px do painel não existe e a medição mente
    browser = await chromium.launch({ channel: 'msedge', headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] })
  } catch (err) {
    stop()
    fail(2, `não consegui abrir o Edge (${err.message.split('\n')[0]}). Instale o Microsoft Edge ou ajuste o canal.`)
  }
} catch (err) {
  stop()
  fail(2, err.message)
}

const bridgeSource = fs.readFileSync(path.join(root, 'scripts', 'visual-fixtures', 'bridge.js'), 'utf8')

/** Roda dentro da página: devolve estouros e a medição de bordas. */
function measure() {
  const vw = window.innerWidth
  const SHELL = '.shell, .shell-main, .topbar, .content'
  const scrolls = (el) => !el.matches(SHELL) && /(auto|scroll|hidden|clip)/.test(getComputedStyle(el).overflowX)
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) if (scrolls(p)) return true
    return false
  }
  // Dentro do .content o limite é a área útil dele (sem a barra de rolagem); fora, a janela.
  const content = document.querySelector('.content')
  const contentRight = content ? content.getBoundingClientRect().left + content.clientWidth : vw
  const limitFor = (el) => (content && el !== content && content.contains(el) ? contentRight : vw)
  const describe = (el) => {
    const cls = typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : ''
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30)
    return `${el.tagName.toLowerCase()}${cls}${text ? ` "${text}"` : ''}`
  }
  const over = []
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) continue
    const s = getComputedStyle(el)
    if (s.display === 'none' || s.visibility === 'hidden') continue
    if (r.right > limitFor(el) + 1 && !inScroller(el)) over.push({ node: el, el: describe(el), right: Math.round(r.right) })
  }
  // só o mais externo de cada cadeia (os filhos de um estouro estouram junto)
  const outer = over.filter((o) => !over.some((p) => p.node !== o.node && p.node.contains(o.node))).map(({ el, right }) => ({ el, right }))
  const scroll = []
  for (const sel of ['.shell', '.shell-main', '.topbar', '.content']) {
    const el = document.querySelector(sel)
    if (el && el.scrollWidth > el.clientWidth + 1) scroll.push({ el: sel, scrollWidth: el.scrollWidth, clientWidth: el.clientWidth })
  }
  const bar = document.querySelector('.topbar-inner') || document.querySelector('.topbar')
  const body = document.querySelector('.content-inner')
  const align = bar && body ? { bar: [Math.round(bar.getBoundingClientRect().left), Math.round(bar.getBoundingClientRect().right)], body: [Math.round(body.getBoundingClientRect().left), Math.round(body.getBoundingClientRect().right)] } : null
  // Alvos de clique abaixo de 24x24 (WCAG 2.2, 2.5.8). Isentos: o que está oculto ou é `sr-only` (1 px) e links em linha.
  const small = []
  for (const el of document.querySelectorAll('button, [role=button], [role=switch], [role=radio], [role=tab], a[href], input, select')) {
    const r = el.getBoundingClientRect()
    const st = getComputedStyle(el)
    if (st.display === 'none' || st.visibility === 'hidden' || r.width <= 1 || r.height <= 1) continue
    if (el.tagName === 'A' && st.display === 'inline') continue
    if (r.width < 24 || r.height < 24) {
      // `elementFromPoint` só enxerga o que está na janela: traz o elemento para a vista antes de sondar.
      el.scrollIntoView({ block: 'center', inline: 'center' })
      const r2 = el.getBoundingClientRect()
      // A área de clique pode passar do retângulo do elemento (pseudo-elemento `::after`): sonda para fora até sair dele.
      const hit = (x, y) => el.contains(document.elementFromPoint(x, y))
      const cx = r2.left + r2.width / 2
      const cy = r2.top + r2.height / 2
      let up = 0
      let down = 0
      while (up < 8 && hit(cx, r2.top - up - 1)) up++
      while (down < 8 && hit(cx, r2.bottom + down)) down++
      let left = 0
      let right = 0
      while (left < 8 && hit(r2.left - left - 1, cy)) left++
      while (right < 8 && hit(r2.right + right, cy)) right++
      const w = r2.width + left + right
      const h = r2.height + up + down
      if (w < 24 || h < 24) small.push({ el: describe(el), w: Math.round(w), h: Math.round(h) })
    }
  }
  const glance = document.querySelector('.glance')
  const glanceBottom = glance ? Math.round(glance.getBoundingClientRect().bottom) : null
  return { over: outer, scroll, align, glanceBottom, small }
}

const SCREENS = [
  { id: 'projetos-grade', run: async (page) => { await page.getByRole('radio', { name: 'Grade' }).click() } },
  { id: 'projetos-lista', run: async (page) => { await page.getByRole('radio', { name: 'Lista' }).click() } },
  ...[
    ['detalhe-geral', 'Visão geral'],
    ['detalhe-economia', 'Economia de tokens'],
    ['detalhe-historico', 'Histórico'],
    ['detalhe-manutencao', 'Manutenção'],
  ].map(([id, tab]) => ({
    id,
    run: async (page) => {
      await page.getByRole('radio', { name: 'Grade' }).click()
      await page.locator('.project-card-name', { hasText: /^juriflux$/ }).click()
      await page.getByRole('tab', { name: tab }).click()
    },
  })),
  { id: 'atividade', run: async (page) => { await page.getByRole('button', { name: 'Atividade' }).first().click() } },
  { id: 'atividade-sessoes', run: async (page) => { await page.getByRole('button', { name: 'Atividade' }).first().click(); await page.getByRole('radiogroup', { name: 'Visão' }).getByRole('radio', { name: 'Sessões' }).click(); await page.locator('.session-head').first().click() } },
  { id: 'conexoes', run: async (page) => { await page.getByRole('button', { name: 'Conexões' }).first().click() } },
  { id: 'preferencias', run: async (page) => { await page.getByRole('button', { name: 'Preferências' }).first().click() } },
  { id: 'como-funciona', run: async (page) => { await page.getByRole('button', { name: 'Como funciona' }).first().click() } },
  { id: 'paleta', run: async (page) => { await page.keyboard.press('Control+k'); await page.getByRole('combobox', { name: 'Buscar comando' }).waitFor() } },
  { id: 'atalhos', run: async (page) => { await page.keyboard.press('Shift+?') ; await page.getByRole('dialog', { name: 'Atalhos de teclado' }).waitFor() } },
  { id: 'onboarding', url: '/?onboarding=1', run: async () => {} },
]

const screens = only.length ? SCREENS.filter((s) => only.includes(s.id)) : SCREENS
const report = []
if (shotsDir) fs.mkdirSync(shotsDir, { recursive: true })

for (const width of widths) {
  const context = await browser.newContext({ viewport: { width, height: HEIGHT } })
  await context.addInitScript({ content: bridgeSource })
  for (const screen of screens) {
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    try {
      await page.goto(`http://localhost:${PORT}${screen.url ?? '/'}`)
      await page.waitForSelector('.shell, .onboarding', { timeout: 8000 })
      await screen.run(page)
      await page.waitForTimeout(350)
      const result = await page.evaluate(measure)
      report.push({ width, screen: screen.id, ...result, errors })
      if (shotsDir) await page.screenshot({ path: path.join(shotsDir, `${screen.id}-${width}.png`) })
    } catch (err) {
      report.push({ width, screen: screen.id, over: [], scroll: [], align: null, small: [], errors: [...errors, `falha ao percorrer a tela: ${err.message.split('\n')[0]}`] })
    }
    await page.close()
  }
  await context.close()
}

await browser.close()
stop()

if (asJson) {
  console.log(JSON.stringify(report, null, 2))
} else {
  let bad = 0
  for (const r of report) {
    const problems = r.over.length + r.scroll.length + r.errors.length + (r.small?.length ?? 0)
    bad += problems
    const mark = problems === 0 ? 'ok ' : 'XX '
    console.log(`${mark}${String(r.width).padStart(4)} px  ${r.screen}`)
    for (const o of r.over.slice(0, 6)) console.log(`      estoura: ${o.el} (direita em ${o.right})`)
    if (r.over.length > 6) console.log(`      ... e mais ${r.over.length - 6}`)
    for (const t of r.small ?? []) console.log(`      alvo pequeno: ${t.el} (${t.w}x${t.h})`)
    for (const s of r.scroll) console.log(`      rola: ${s.el} scrollWidth ${s.scrollWidth} > clientWidth ${s.clientWidth}`)
    for (const e of r.errors) console.log(`      erro: ${e}`)
  }
  for (const r of report.filter((x) => x.glanceBottom !== null && x.screen === 'detalhe-geral')) console.log(`faixa de relance a ${r.width} px: termina em y=${r.glanceBottom} (altura da janela ${HEIGHT})`)
  const wide = report.filter((r) => r.width >= 2000 && r.align)
  for (const r of wide) {
    const d = Math.max(Math.abs(r.align.bar[0] - r.align.body[0]), Math.abs(r.align.bar[1] - r.align.body[1]))
    console.log(`bordas a ${r.width} px (${r.screen}): topbar ${r.align.bar.join('-')} x conteúdo ${r.align.body.join('-')} (diferença ${d} px)`)
  }
  console.log(`\n${report.length} medições, ${bad} problema(s).`)
  process.exitCode = bad === 0 ? 0 : 1
}

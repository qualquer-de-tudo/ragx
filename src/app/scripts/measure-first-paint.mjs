#!/usr/bin/env node
/**
 * Mede a primeira pintura do painel (RAGX-0182) com `getSnapshot` atrasado em 3 s: sem cache (quando o skeleton
 * aparece e se o "Carregando…" em tela cheia some) e com cache (quando o primeiro cartão aparece e se a faixa de dado
 * velho some quando o vivo chega). Precisa de `dist/` (npm run build) e do Edge; mesma ponte de `visual-check.mjs`.
 *
 *   node scripts/measure-first-paint.mjs [--delay 3000]
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const args = process.argv.slice(2)
const delay = Number(args.includes('--delay') ? args[args.indexOf('--delay') + 1] : 3000)
const PORT = 4175
const vite = spawn(process.execPath, [path.join(root, 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--port', String(PORT), '--strictPort'], { cwd: root, stdio: 'ignore' })
for (let i = 0; i < 60; i++) {
  const ok = await new Promise((r) => http.get(`http://localhost:${PORT}/`, (res) => (res.resume(), r(true))).on('error', () => r(false)))
  if (ok) break
  await new Promise((r) => setTimeout(r, 250))
}
try {
  const browser = await chromium.launch({ channel: 'msedge', headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] })
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  await context.addInitScript({ content: fs.readFileSync(path.join(root, 'scripts', 'visual-fixtures', 'bridge.js'), 'utf8') })
  const url = `http://localhost:${PORT}/?snapshotDelay=${delay}`

  const t = async (page, selector) => {
    const start = Date.now()
    await page.waitForSelector(selector, { timeout: delay + 8000 })
    return Date.now() - start
  }

  // 1) sem cache
  const a = await context.newPage()
  await a.goto(url, { waitUntil: 'commit' })
  const skeleton = await t(a, '.skeleton-card')
  const bootText = await a.evaluate(() => (document.body.innerText.includes('Carregando…') ? 'SIM' : 'não'))
  const cardsLate = await t(a, '.project-card')
  console.log(`sem cache: skeleton em ${skeleton} ms; "Carregando…" na tela: ${bootText}; primeiro .project-card em ${skeleton + cardsLate} ms (atraso do snapshot: ${delay} ms)`)
  await a.waitForTimeout(500) // deixa o cache ser gravado
  console.log(`tamanho do cache: ${await a.evaluate(() => (localStorage.getItem('ragx.snapshot.v1') ?? '').length)} caracteres (12 projetos, série de 14 dias)`)
  await a.close()

  // 2) com cache (mesmo contexto: o localStorage ficou)
  const b = await context.newPage()
  await b.goto(url, { waitUntil: 'commit' })
  const first = await t(b, '.project-card')
  const banner = await b.evaluate(() => document.querySelector('.stale-banner')?.textContent ?? null)
  console.log(`com cache: primeiro .project-card em ${first} ms; faixa: ${JSON.stringify(banner)}`)
  const cardNode = await b.evaluateHandle(() => document.querySelector('.project-card'))
  await b.waitForSelector('.stale-banner', { state: 'detached', timeout: delay + 8000 })
  const same = await b.evaluate((n) => n === document.querySelector('.project-card'), cardNode)
  console.log(`com cache: a faixa sumiu quando o vivo chegou; o cartão é o mesmo nó (sem remontar): ${same}`)
  await browser.close()
} finally {
  vite.kill()
}

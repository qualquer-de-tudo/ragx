#!/usr/bin/env node
/**
 * Sonda do harness visual (RAGX-0181): abre uma tela numa largura e imprime, de um seletor para cima, a largura e o
 * `display` de cada ancestral, para achar quem alarga a coluna.
 *
 *   node scripts/visual-probe.mjs --screen atividade --width 450 --selector ".activity-feed"
 *
 * Reaproveita o servidor do `vite preview` e a ponte simulada de `visual-check.mjs`; precisa de `dist/` e do Edge.
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const args = process.argv.slice(2)
const opt = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback)
const width = Number(opt('--width', '450'))
const selector = opt('--selector', '.content-inner')
const nav = { atividade: 'Atividade', conexoes: 'Conexões', 'como-funciona': 'Como funciona' }[opt('--screen', 'atividade')]
const PORT = Number(opt('--port', '4174'))

const vite = spawn(process.execPath, [path.join(root, 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--port', String(PORT), '--strictPort'], { cwd: root, stdio: 'ignore' })
const ready = async () => {
  for (let i = 0; i < 60; i++) {
    const ok = await new Promise((r) => http.get(`http://localhost:${PORT}/`, (res) => (res.resume(), r(true))).on('error', () => r(false)))
    if (ok) return
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error('servidor não subiu')
}
try {
  await ready()
  const browser = await chromium.launch({ channel: 'msedge', headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] })
  const context = await browser.newContext({ viewport: { width, height: 800 } })
  await context.addInitScript({ content: fs.readFileSync(path.join(root, 'scripts', 'visual-fixtures', 'bridge.js'), 'utf8') })
  const page = await context.newPage()
  await page.goto(`http://localhost:${PORT}/`)
  await page.waitForSelector('.shell')
  if (nav) await page.getByRole('button', { name: nav }).first().click()
  await page.waitForTimeout(300)
  const chain = await page.evaluate((sel) => {
    const out = []
    for (let el = document.querySelector(sel); el; el = el.parentElement) {
      const s = getComputedStyle(el)
      out.push(`${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).trim().split(/\s+/).join('.') : ''}  w=${Math.round(el.getBoundingClientRect().width)} display=${s.display} cols=${s.gridTemplateColumns.slice(0, 40)}`)
      if (el.tagName === 'BODY') break
    }
    return out
  }, selector)
  console.log(chain.join('\n'))
  await browser.close()
} finally {
  vite.kill()
}

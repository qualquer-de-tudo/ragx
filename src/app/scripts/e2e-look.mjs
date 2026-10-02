#!/usr/bin/env node
/**
 * Captura de tela das telas do painel REAL instalado (Playwright), com pasta de dados temporária: nada seu é lido ou gravado.
 *
 *   node scripts/e2e-look.mjs --shots <pasta> [--exe <caminho>]
 *
 * Tira Conexões, Como funciona e Atividade, e imprime a versão e o texto do card "Ajuste automático" (que usa os projetos
 * e os perfis desta máquina, então o texto é o estado real).
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { _electron as electron } from 'playwright-core'

const args = process.argv.slice(2)
const opt = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback)
const exe = opt('--exe', path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'RAGX Painel', 'RAGX Painel.exe'))
const shots = opt('--shots', null)
if (!shots) {
  console.error('e2e-look: informe --shots <pasta>')
  process.exit(2)
}
fs.mkdirSync(shots, { recursive: true })

const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-look-'))
fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ onboardingDone: true, autoUpdate: false, autoSetup: false }))
const app = await electron.launch({ executablePath: exe, args: [`--user-data-dir=${userData}`], timeout: 60_000 })
try {
  const page = await app.firstWindow()
  await page.setViewportSize({ width: 1280, height: 1100 }).catch(() => {})
  const nav = (name) => page.getByRole('button', { name }).first()
  await nav('Conexões').waitFor({ timeout: 60_000 })

  const shot = (name) => page.screenshot({ path: path.join(shots, `${name}.png`), timeout: 10_000 }).catch(() => console.log(`(sem captura de ${name})`))

  await nav('Conexões').click()
  await page.getByRole('heading', { name: 'Ajuste automático' }).waitFor({ timeout: 30_000 })
  await page.waitForTimeout(2500) // deixa a checagem das conexões terminar
  console.log('Ajuste automático:', (await page.locator('.auto-card').innerText()).replace(/\n+/g, ' | '))
  await shot('conexoes')

  await nav('Como funciona').click()
  await page.getByRole('heading', { name: 'O caminho do dado' }).waitFor({ timeout: 15_000 })
  await shot('como-funciona')

  await nav('Atividade').click()
  await page.getByRole('heading', { name: 'Atividade', level: 1 }).waitFor({ timeout: 15_000 })
  await page.waitForTimeout(1500)
  await shot('atividade')

  const botoes = await page.locator('.nav-item .nav-label').allInnerTexts()
  console.log('Barra lateral, de cima para baixo:', botoes.join(' > '))
  await nav('Preferências').click()
  await page.locator('.update-status').waitFor({ timeout: 15_000 })
  console.log('Preferências:', await page.locator('.update-status').innerText())
} finally {
  await app.close().catch(() => {})
  fs.rmSync(userData, { recursive: true, force: true })
}

#!/usr/bin/env node
/**
 * Teste ponta a ponta da atualização do painel, no painel REAL (o `.exe` instalado), pelo Playwright.
 *
 *   node scripts/e2e-update.mjs [--exe "C:/Users/<voce>/AppData/Local/Programs/RAGX Painel/RAGX Painel.exe"]
 *                               [--install] [--shots <pasta>] [--timeout 300]
 *
 * Abre o painel com uma pasta de dados TEMPORÁRIA (`--user-data-dir`): outra trava de instância única e nenhuma preferência
 * sua é lida ou gravada, então roda ao lado do painel que você já tem aberto. Em Preferências: confere o estado, clica
 * "Verificar agora", espera "versão X disponível", clica "Baixar atualização" e espera "baixada, pronta para instalar".
 * Sem `--install` para aí (fecha o painel de teste). Com `--install`, clica "Instalar e reiniciar": o instalador troca o painel
 * instalado de verdade (e fecha o que estiver aberto), então só use quando quiser mesmo atualizar.
 *
 * Sai com 0 se tudo funcionou, 1 se algum passo falhou (com a captura de tela do ponto), 2 se faltar o `.exe` ou o Playwright.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const args = process.argv.slice(2)
const opt = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback)
const exe = opt('--exe', path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'RAGX Painel', 'RAGX Painel.exe'))
const install = args.includes('--install')
const shots = opt('--shots', null)
const timeoutMs = Number(opt('--timeout', '300')) * 1000

function fail(code, message) {
  console.error(`e2e-update: ${message}`)
  process.exit(code)
}

if (!fs.existsSync(exe)) fail(2, `não achei o painel em ${exe} (use --exe).`)
let electron
try {
  ;({ _electron: electron } = await import('playwright-core'))
} catch {
  fail(2, 'playwright-core não está instalado (`npm install`).')
}
if (shots) fs.mkdirSync(shots, { recursive: true })

const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-e2e-'))
// Onboarding feito: senão o painel abre na configuração inicial, sem barra lateral.
fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ onboardingDone: true }))

const app = await electron.launch({ executablePath: exe, args: [`--user-data-dir=${userData}`], timeout: 60_000 })
const page = await app.firstWindow()
await page.setViewportSize({ width: 1280, height: 900 }).catch(() => {})

async function shot(name) {
  if (shots) await page.screenshot({ path: path.join(shots, `${name}.png`) })
}

const status = () => page.locator('.update-status').innerText()
let step = 'abrir'
try {
  await page.getByRole('button', { name: 'Preferências' }).first().waitFor({ timeout: 60_000 })
  step = 'abrir Preferências'
  await page.getByRole('button', { name: 'Preferências' }).first().click()
  await page.locator('.update-status').waitFor({ timeout: 15_000 })
  console.log(`1. Preferências aberta. ${await status()}`)
  await shot('1-preferencias')

  step = 'Verificar agora'
  await page.getByRole('button', { name: 'Verificar agora' }).click()
  await page.waitForFunction(
    () => /disponível|baixada/.test(document.querySelector('.update-status')?.textContent ?? ''),
    null,
    { timeout: 60_000 },
  )
  console.log(`2. Depois de "Verificar agora": ${await status()}`)
  await shot('2-disponivel')

  step = 'Baixar atualização'
  await page.getByRole('button', { name: 'Baixar atualização' }).click()
  await page.waitForFunction(() => /baixada, pronta/.test(document.querySelector('.update-status')?.textContent ?? ''), null, {
    timeout: timeoutMs,
  })
  console.log(`3. Depois de "Baixar atualização": ${await status()}`)
  await shot('3-baixada')

  if (install) {
    step = 'Instalar e reiniciar'
    console.log('4. Clicando em "Instalar e reiniciar": o painel fecha, o instalador troca a versão e o painel reabre.')
    await page.getByRole('button', { name: 'Instalar e reiniciar' }).click()
    await app.waitForEvent('close', { timeout: 60_000 }).catch(() => {})
  } else {
    console.log('4. Sem --install: parei antes de instalar.')
    await app.close()
  }
  console.log('e2e-update: ok')
  process.exit(0)
} catch (err) {
  await shot(`falha-${step.replace(/\W+/g, '-')}`).catch(() => {})
  let texto = ''
  try {
    texto = await status()
  } catch {
    /* sem a tela de Preferências */
  }
  console.error(`e2e-update: falhou em "${step}": ${err instanceof Error ? err.message : String(err)}\n  estado na tela: ${texto}`)
  await app.close().catch(() => {})
  process.exit(1)
} finally {
  fs.rmSync(userData, { recursive: true, force: true })
}

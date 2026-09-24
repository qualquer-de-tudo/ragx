// Prepara resources/ragx-bundle/ para o electron-builder (extraResources):
//   uv.exe          extraído do zip oficial da Astral, com o SHA256 publicado conferido
//   ragx-*.whl      construído a partir deste repositório (`uv build --wheel`)
//   bundle.json     versões + SHA256 dos dois arquivos finais, lidos pelo painel
//                   (electron/bootstrap/bundle.ts) antes de executar qualquer coisa.
//
// O hash protege contra corrupção, não contra adulteração (isso exigiria assinatura).
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import {
  copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync,
  renameSync, rmSync, writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// Versão FIXA do uv: build reprodutível. Para atualizar, troque aqui e rode de novo.
const UV_VERSION = '0.12.18'
const PYTHON = '3.12'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = resolve(appDir, '..', '..')
const outDir = join(appDir, 'resources', 'ragx-bundle')
// Monta tudo aqui e só troca pela pasta final no fim: uma falha no meio (rede,
// `uv` ausente) não pode apagar um pacote que já funcionava.
const stageDir = `${outDir}.staging`

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts })
  if (r.error) throw new Error(`falha ao executar ${cmd}: ${r.error.message}`)
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(' ')} terminou com código ${r.status}`)
}

async function baixar(url) {
  const res = await fetch(url, { redirect: 'follow' })
  if (!res.ok) throw new Error(`download falhou (${res.status}): ${url}`)
  return Buffer.from(await res.arrayBuffer())
}

async function main() {
  rmSync(stageDir, { recursive: true, force: true })
  mkdirSync(stageDir, { recursive: true })

  // 1. wheel do ragx (py3-none-any) a partir da raiz do repositório
  const distDir = join(repoRoot, 'dist')
  const antes = new Set(existsSync(distDir) ? readdirSync(distDir) : [])
  run('uv', ['build', '--wheel'], { cwd: repoRoot })
  const wheels = readdirSync(distDir)
    .filter((f) => f.endsWith('.whl'))
    .map((f) => ({ f, novo: !antes.has(f) }))
  // Prefere o wheel recém-criado; se já existia igual, `uv` o reescreveu, então serve.
  const wheelFile = (wheels.find((w) => w.novo) ?? wheels.sort((a, b) => a.f.localeCompare(b.f)).at(-1))?.f
  if (!wheelFile) throw new Error('uv build --wheel não produziu nenhum .whl em dist/')
  copyFileSync(join(distDir, wheelFile), join(stageDir, wheelFile))
  const version = /^ragx-([^-]+)-/.exec(wheelFile)?.[1]
  if (!version) throw new Error(`nome de wheel inesperado: ${wheelFile}`)

  // 2. uv.exe: zip oficial + .sha256 publicado ao lado
  const base = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}`
  const zipName = 'uv-x86_64-pc-windows-msvc.zip'
  const tmp = mkdtempSync(join(tmpdir(), 'ragx-uv-'))
  try {
    const zipPath = join(tmp, zipName)
    const zipBytes = await baixar(`${base}/${zipName}`)
    const esperado = (await baixar(`${base}/${zipName}.sha256`)).toString('utf8').trim().split(/\s+/)[0].toLowerCase()
    const obtido = createHash('sha256').update(zipBytes).digest('hex')
    if (obtido !== esperado) {
      throw new Error(`SHA256 do ${zipName} diverge: esperado ${esperado}, obtido ${obtido}`)
    }
    writeFileSync(zipPath, zipBytes)
    // `tar` (bsdtar) vem no Windows 10+ e no runner windows-latest e lê .zip.
    run('tar', ['-xf', zipPath, '-C', tmp])
    const uvExe = join(tmp, 'uv.exe')
    if (!existsSync(uvExe)) throw new Error(`uv.exe não estava no ${zipName}`)
    copyFileSync(uvExe, join(stageDir, 'uv.exe'))
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }

  // 3. bundle.json — o hash é do arquivo FINAL que vai para o instalador
  const manifesto = {
    version,
    python: PYTHON,
    uv: { file: 'uv.exe', sha256: sha256(join(stageDir, 'uv.exe')) },
    wheel: { file: wheelFile, sha256: sha256(join(stageDir, wheelFile)) },
  }
  writeFileSync(join(stageDir, 'bundle.json'), JSON.stringify(manifesto, null, 2) + '\n')
  rmSync(outDir, { recursive: true, force: true })
  renameSync(stageDir, outDir)
  console.log(`bundle pronto em ${outDir}\n${JSON.stringify(manifesto, null, 2)}`)
}

main().catch((e) => {
  console.error(`prepare-bundle: ${e.message}`)
  process.exit(1)
})

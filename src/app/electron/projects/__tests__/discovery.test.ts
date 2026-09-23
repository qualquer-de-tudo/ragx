import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { discoverProjects } from '../discovery'

function mkTmp(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-discovery-test-'))
}

function writeToml(dir: string): void {
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'ragx.toml'), '')
}

describe('discoverProjects - arvore real em tmpdir', () => {
  it('acha um projeto na raiz', () => {
    const root = mkTmp()
    writeToml(root)

    const found = discoverProjects(root, new Set())

    expect(found).toHaveLength(1)
    expect(found[0].path).toBe(root)
    expect(found[0].name).toBe(path.basename(root))
    expect(found[0].alreadyRegistered).toBe(false)
  })

  it('acha um projeto 4 niveis abaixo da raiz (maxDepth padrao)', () => {
    const root = mkTmp()
    const deep = path.join(root, 'a', 'b', 'c', 'd')
    writeToml(deep)

    const found = discoverProjects(root, new Set())

    expect(found.map((f) => f.path)).toEqual([deep])
  })

  it('nao acha um projeto 5 niveis abaixo da raiz (fora do maxDepth padrao)', () => {
    const root = mkTmp()
    const tooDeep = path.join(root, 'a', 'b', 'c', 'd', 'e')
    writeToml(tooDeep)

    const found = discoverProjects(root, new Set())

    expect(found).toEqual([])
  })

  it('pula node_modules e .venv - nao desce nessas pastas mesmo com ragx.toml dentro', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'node_modules', 'x'))
    writeToml(path.join(root, '.venv', 'y'))
    writeToml(path.join(root, 'real-project'))

    const found = discoverProjects(root, new Set())

    expect(found.map((f) => f.name)).toEqual(['real-project'])
  })

  it('nao desce dentro de um projeto ja encontrado', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'proj'))
    writeToml(path.join(root, 'proj', 'vendor', 'outro'))

    const found = discoverProjects(root, new Set())

    expect(found.map((f) => f.name)).toEqual(['proj'])
  })

  it('ordena os achados por nome', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'zeta'))
    writeToml(path.join(root, 'alfa'))

    const found = discoverProjects(root, new Set())

    expect(found.map((f) => f.name)).toEqual(['alfa', 'zeta'])
  })

  it('marca alreadyRegistered quando o caminho ja esta registrado (mesma grafia)', () => {
    const root = mkTmp()
    const projectDir = path.join(root, 'proj')
    writeToml(projectDir)

    const found = discoverProjects(root, new Set([projectDir]))

    expect(found[0].alreadyRegistered).toBe(true)
  })

  it('compara caminhos registrados ignorando maiusculas so no Windows', () => {
    const root = mkTmp()
    const projectDir = path.join(root, 'Projeto')
    writeToml(projectDir)

    const found = discoverProjects(root, new Set([projectDir.toUpperCase()]))

    // No Windows o mesmo caminho com outra grafia ainda conta como
    // registrado; nos outros SOs uma letra diferente é uma pasta diferente.
    expect(found[0].alreadyRegistered).toBe(process.platform === 'win32')
  })

  it('ignora erros de permissao numa subpasta sem derrubar a busca', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'ok-project'))

    const found = discoverProjects(root, new Set(), {
      readdir: (dir) => {
        if (dir.endsWith('sem-permissao')) throw new Error('EACCES')
        if (dir === root) {
          return [
            { name: 'ok-project', isDirectory: true },
            { name: 'sem-permissao', isDirectory: true },
          ]
        }
        return fs.readdirSync(dir, { withFileTypes: true }).map((e) => ({ name: e.name, isDirectory: e.isDirectory() }))
      },
    })

    expect(found.map((f) => f.name)).toEqual(['ok-project'])
  })
})

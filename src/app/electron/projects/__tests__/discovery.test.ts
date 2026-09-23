import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { discoverProjects, type DirEntryLike } from '../discovery'

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

    const { items, truncated } = discoverProjects(root, new Set())

    expect(items).toHaveLength(1)
    expect(items[0].path).toBe(root)
    expect(items[0].name).toBe(path.basename(root))
    expect(items[0].alreadyRegistered).toBe(false)
    expect(truncated).toBe(false)
  })

  it('acha um projeto 4 niveis abaixo da raiz (maxDepth padrao)', () => {
    const root = mkTmp()
    const deep = path.join(root, 'a', 'b', 'c', 'd')
    writeToml(deep)

    const { items } = discoverProjects(root, new Set())

    expect(items.map((f) => f.path)).toEqual([deep])
  })

  it('nao acha um projeto 5 niveis abaixo da raiz (fora do maxDepth padrao)', () => {
    const root = mkTmp()
    const tooDeep = path.join(root, 'a', 'b', 'c', 'd', 'e')
    writeToml(tooDeep)

    const { items } = discoverProjects(root, new Set())

    expect(items).toEqual([])
  })

  it('pula node_modules e .venv - nao desce nessas pastas mesmo com ragx.toml dentro', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'node_modules', 'x'))
    writeToml(path.join(root, '.venv', 'y'))
    writeToml(path.join(root, 'real-project'))

    const { items } = discoverProjects(root, new Set())

    expect(items.map((f) => f.name)).toEqual(['real-project'])
  })

  it('pula pastas de ruido do Windows por nome, sem diferenciar maiusculas', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'AppData', 'x'))
    writeToml(path.join(root, 'Windows', 'y'))
    writeToml(path.join(root, '$Recycle.Bin', 'z'))
    writeToml(path.join(root, 'System Volume Information', 'w'))
    writeToml(path.join(root, 'Program Files', 'p1'))
    writeToml(path.join(root, 'Program Files (x86)', 'p2'))
    writeToml(path.join(root, 'ProgramData', 'p3'))
    writeToml(path.join(root, 'real-project'))

    const { items } = discoverProjects(root, new Set())

    expect(items.map((f) => f.name)).toEqual(['real-project'])
  })

  it('nao desce dentro de um projeto ja encontrado', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'proj'))
    writeToml(path.join(root, 'proj', 'vendor', 'outro'))

    const { items } = discoverProjects(root, new Set())

    expect(items.map((f) => f.name)).toEqual(['proj'])
  })

  it('ordena os achados por nome', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'zeta'))
    writeToml(path.join(root, 'alfa'))

    const { items } = discoverProjects(root, new Set())

    expect(items.map((f) => f.name)).toEqual(['alfa', 'zeta'])
  })

  it('marca alreadyRegistered quando o caminho ja esta registrado (mesma grafia)', () => {
    const root = mkTmp()
    const projectDir = path.join(root, 'proj')
    writeToml(projectDir)

    const { items } = discoverProjects(root, new Set([projectDir]))

    expect(items[0].alreadyRegistered).toBe(true)
  })

  it('compara caminhos registrados ignorando maiusculas so no Windows', () => {
    const root = mkTmp()
    const projectDir = path.join(root, 'Projeto')
    writeToml(projectDir)

    const { items } = discoverProjects(root, new Set([projectDir.toUpperCase()]))

    // No Windows o mesmo caminho com outra grafia ainda conta como
    // registrado; nos outros SOs uma letra diferente é uma pasta diferente.
    expect(items[0].alreadyRegistered).toBe(process.platform === 'win32')
  })

  it('ignora erros de permissao numa subpasta sem derrubar a busca', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'ok-project'))

    const { items } = discoverProjects(root, new Set(), {
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

    expect(items.map((f) => f.name)).toEqual(['ok-project'])
  })
})

describe('discoverProjects - orcamento de pastas (maxDirs, fix round 1)', () => {
  /** Uma raiz falsa achatada com `count` subpastas diretas, sem `ragx.toml` em nenhuma. */
  function fakeFlatTree(count: number): (dir: string) => DirEntryLike[] {
    const names = Array.from({ length: count }, (_, i) => `sub-${String(i)}`)
    return (dir: string): DirEntryLike[] => {
      if (dir === 'root') return names.map((name) => ({ name, isDirectory: true }))
      return [] // pastas-folha: vazias, sem ragx.toml
    }
  }

  it('para a busca e marca truncated quando o orcamento de pastas e atingido', () => {
    const result = discoverProjects('root', new Set(), {
      readdir: fakeFlatTree(20),
      exists: () => true,
      maxDirs: 5,
    })

    expect(result.truncated).toBe(true)
    // 1 (a raiz) + 4 subpastas visitadas = 5, o orcamento inteiro.
    expect(result.items).toEqual([])
  })

  it('nao trunca quando o orcamento nunca e atingido', () => {
    const result = discoverProjects('root', new Set(), {
      readdir: fakeFlatTree(20),
      exists: () => true,
      maxDirs: 5000,
    })

    expect(result.truncated).toBe(false)
  })

  it('o orcamento padrao (5000) e generoso o bastante pra uma arvore normal de projeto nao truncar', () => {
    const root = mkTmp()
    writeToml(path.join(root, 'proj'))
    for (let i = 0; i < 50; i += 1) {
      fs.mkdirSync(path.join(root, `pasta-${String(i)}`), { recursive: true })
    }

    const result = discoverProjects(root, new Set())

    expect(result.truncated).toBe(false)
  })
})

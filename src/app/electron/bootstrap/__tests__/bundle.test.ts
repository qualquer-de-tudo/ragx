import { describe, expect, it } from 'vitest'
import path from 'node:path'
import { BundleError, findBundleDir, loadBundle, uvCommand } from '../bundle'

const res = path.join('C:', 'App', 'resources')
const dir = path.join(res, 'ragx-bundle')
const json = JSON.stringify({
  version: '1.0.0b3',
  python: '3.12',
  uv: { file: 'uv.exe', sha256: 'AAA' },
  wheel: { file: 'ragx-1.0.0b3-py3-none-any.whl', sha256: 'bbb' },
})
const files = new Set([
  path.join(dir, 'bundle.json'),
  path.join(dir, 'uv.exe'),
  path.join(dir, 'ragx-1.0.0b3-py3-none-any.whl'),
])
const base = {
  resourcesPath: res,
  devDir: path.join('C:', 'nada'),
  exists: (p: string) => files.has(p),
  readFile: () => json,
  sha256File: (p: string) => (p.endsWith('uv.exe') ? 'aaa' : 'bbb'),
}

function codeOf(fn: () => unknown): string | undefined {
  try {
    fn()
  } catch (e) {
    return (e as BundleError).code
  }
  return undefined
}

describe('findBundleDir', () => {
  it('acha o pacote em resources', () => expect(findBundleDir(base)).toBe(dir))
  it('sem pacote devolve null', () => expect(findBundleDir({ ...base, exists: () => false })).toBeNull())
})

describe('loadBundle', () => {
  it('devolve os caminhos absolutos quando os hashes conferem (sem diferenciar caixa)', () => {
    const b = loadBundle(base)
    expect(b.uvPath).toBe(path.join(dir, 'uv.exe'))
    expect(b.wheelPath).toBe(path.join(dir, 'ragx-1.0.0b3-py3-none-any.whl'))
    expect(b.python).toBe('3.12')
    expect(b.version).toBe('1.0.0b3')
  })

  it('pacote ausente lança missing', () => {
    expect(codeOf(() => loadBundle({ ...base, exists: () => false }))).toBe('missing')
  })

  it('hash diferente lança hash', () => {
    expect(codeOf(() => loadBundle({ ...base, sha256File: () => 'ffff' }))).toBe('hash')
  })

  it('arquivo do pacote ausente lança missing', () => {
    const semUv = new Set(files)
    semUv.delete(path.join(dir, 'uv.exe'))
    expect(codeOf(() => loadBundle({ ...base, exists: (p) => semUv.has(p) }))).toBe('missing')
  })

  it('bundle.json incompleto ou ilegível lança missing', () => {
    expect(codeOf(() => loadBundle({ ...base, readFile: () => '{"version":"1"}' }))).toBe('missing')
    expect(codeOf(() => loadBundle({ ...base, readFile: () => 'nao-json' }))).toBe('missing')
  })

  it('não deixa o bundle.json apontar para fora da pasta do pacote', () => {
    const malicioso = JSON.stringify({
      version: '1',
      python: '3.12',
      uv: { file: '..\\..\\evil.exe', sha256: 'aaa' },
      wheel: { file: 'ragx-1.0.0b3-py3-none-any.whl', sha256: 'bbb' },
    })
    // vira `evil.exe` dentro do pacote, que não existe
    expect(codeOf(() => loadBundle({ ...base, readFile: () => malicioso }))).toBe('missing')
  })
})

describe('uvCommand', () => {
  it('usa o uv.exe do pacote', () => expect(uvCommand(base)).toBe(path.join(dir, 'uv.exe')))
  it('sem pacote cai no uv puro', () => expect(uvCommand({ ...base, exists: () => false })).toBe('uv'))
})

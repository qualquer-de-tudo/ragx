import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { readGitHeadCached, readGitHeadFromFiles, resetGitCache } from '../git-files'

const H1 = 'a'.repeat(40)
const H2 = 'b'.repeat(40)
const H3 = 'c'.repeat(64)

let root: string

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-gitfiles-'))
  resetGitCache()
})
afterEach(() => fs.rmSync(root, { recursive: true, force: true }))

function write(rel: string, text: string): string {
  const file = path.join(root, rel)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, text)
  return file
}

describe('readGitHeadFromFiles', () => {
  it('ramo com a ref solta', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    write('.git/refs/heads/main', `${H1}\n`)
    expect(readGitHeadFromFiles(root)).toEqual({ branch: 'main', commit: H1 })
  })

  it('ramo com barra no nome', () => {
    write('.git/HEAD', 'ref: refs/heads/feat/v2\r\n') // CRLF do Windows
    write('.git/refs/heads/feat/v2', `${H2}\r\n`)
    expect(readGitHeadFromFiles(root)).toEqual({ branch: 'feat/v2', commit: H2 })
  })

  it('ref empacotada (packed-refs), ignorando comentários e linhas `^`', () => {
    write('.git/HEAD', 'ref: refs/heads/dev\n')
    write('.git/packed-refs', `# pack-refs with: peeled fully-peeled sorted\n${H1} refs/heads/main\n${H2} refs/heads/dev\n^${H3}\n`)
    expect(readGitHeadFromFiles(root)).toEqual({ branch: 'dev', commit: H2 })
  })

  it('a ref solta vence a empacotada', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    write('.git/refs/heads/main', `${H2}\n`)
    write('.git/packed-refs', `${H1} refs/heads/main\n`)
    expect(readGitHeadFromFiles(root)).toEqual({ branch: 'main', commit: H2 })
  })

  it('HEAD destacado: branch null; aceita hash de 64 caracteres (sha256)', () => {
    write('.git/HEAD', `${H1}\n`)
    expect(readGitHeadFromFiles(root)).toEqual({ branch: null, commit: H1 })
    write('.git/HEAD', `${H3}\n`)
    expect(readGitHeadFromFiles(root)).toEqual({ branch: null, commit: H3 })
  })

  it('repositório recém-criado, sem commit: null', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    expect(readGitHeadFromFiles(root)).toBeNull()
  })

  it('pasta sem .git em nenhum ancestral: null; pasta que nem existe: unsupported', () => {
    // dentro da pasta temporária não há `.git` acima (o tmp não é um repositório)
    fs.mkdirSync(path.join(root, 'solto'))
    expect(readGitHeadFromFiles(path.join(root, 'solto'))).toBeNull()
    expect(readGitHeadFromFiles(path.join(root, 'nao-existe'))).toBe('unsupported')
  })

  it('subpasta de um repositório lê o `.git` do ancestral (como o `git rev-parse` fazia)', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    write('.git/refs/heads/main', `${H1}\n`)
    fs.mkdirSync(path.join(root, 'pacotes', 'a'), { recursive: true })
    expect(readGitHeadFromFiles(path.join(root, 'pacotes', 'a'))).toEqual({ branch: 'main', commit: H1 })
  })

  it('`.git` como arquivo `gitdir:` (submódulo) com caminho relativo e barras do Windows', () => {
    write('modulo/.git', 'gitdir: ..\\.git\\modules\\modulo\n')
    write('.git/modules/modulo/HEAD', 'ref: refs/heads/main\n')
    write('.git/modules/modulo/refs/heads/main', `${H1}\n`)
    expect(readGitHeadFromFiles(path.join(root, 'modulo'))).toEqual({ branch: 'main', commit: H1 })
  })

  it('worktree: HEAD no gitdir do worktree, refs no `commondir`', () => {
    write('principal/.git/refs/heads/main', `${H1}\n`)
    write('principal/.git/refs/heads/outro', `${H2}\n`)
    write('principal/.git/worktrees/wt/HEAD', 'ref: refs/heads/outro\n')
    write('principal/.git/worktrees/wt/commondir', '../..\n')
    write('wt/.git', `gitdir: ${path.join(root, 'principal', '.git', 'worktrees', 'wt')}\n`)
    expect(readGitHeadFromFiles(path.join(root, 'wt'))).toEqual({ branch: 'outro', commit: H2 })
  })

  describe('endurecimento: qualquer dúvida vira unsupported', () => {
    it('hash inválido na ref solta ou no HEAD destacado', () => {
      write('.git/HEAD', 'ref: refs/heads/main\n')
      write('.git/refs/heads/main', 'nao-e-um-hash\n')
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
      write('.git/HEAD', 'zzzz\n')
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
      write('.git/HEAD', `${H1.slice(0, 39)}\n`) // 39 caracteres
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
    })

    it('`ref:` com `..`, caminho absoluto ou barra invertida', () => {
      for (const ref of ['refs/heads/../../x', '/etc/passwd', 'C:/x', 'refs\\heads\\main', 'refs/heads//x', 'main']) {
        write('.git/HEAD', `ref: ${ref}\n`)
        expect(readGitHeadFromFiles(root)).toBe('unsupported')
      }
    })

    it('ref que aponta para outra `ref:`', () => {
      write('.git/HEAD', 'ref: refs/heads/main\n')
      write('.git/refs/heads/main', 'ref: refs/heads/outro\n')
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
    })

    it('reftable (pasta ou configuração)', () => {
      write('.git/HEAD', 'ref: refs/heads/main\n')
      write('.git/refs/heads/main', `${H1}\n`)
      write('.git/config', '[extensions]\n\trefStorage = reftable\n')
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
      fs.rmSync(path.join(root, '.git', 'config'))
      fs.mkdirSync(path.join(root, '.git', 'reftable'))
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
    })

    it('arquivo maior que 64 KB, HEAD vazio ou ausente, `.git` ilegível', () => {
      write('.git/HEAD', 'ref: refs/heads/main\n')
      write('.git/refs/heads/main', 'a'.repeat(70 * 1024))
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
      write('.git/HEAD', '')
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
      fs.rmSync(path.join(root, '.git', 'HEAD'))
      expect(readGitHeadFromFiles(root)).toBe('unsupported')
      write('outra/.git', 'isto nao e gitdir')
      expect(readGitHeadFromFiles(path.join(root, 'outra'))).toBe('unsupported')
    })

    it('nunca lança, mesmo com um sistema de arquivos que falha', () => {
      const quebrado = {
        stat: () => {
          throw new Error('EIO')
        },
        readText: () => {
          throw new Error('EIO')
        },
      }
      expect(readGitHeadFromFiles(root, quebrado)).toBe('unsupported')
    })
  })
})

describe('readGitHeadCached', () => {
  it('sem mudança devolve o MESMO objeto; depois de o HEAD ou a ref mudarem, um novo', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    const ref = write('.git/refs/heads/main', `${H1}\n`)
    const a = readGitHeadCached(root)
    const b = readGitHeadCached(root)
    expect(a).toEqual({ branch: 'main', commit: H1 })
    expect(b).toBe(a) // a identidade é estável: a RAGX-0175 a usa para não re-renderizar

    fs.writeFileSync(ref, `${H2}\n`) // um commit novo muda o arquivo da ref (tamanho igual: o mtime decide)
    const t = Date.now() / 1000 + 5
    fs.utimesSync(ref, t, t)
    const c = readGitHeadCached(root)
    expect(c).toEqual({ branch: 'main', commit: H2 })
    expect(c).not.toBe(a)

    write('.git/refs/heads/outro', `${H3.slice(0, 40)}\n`)
    fs.writeFileSync(path.join(root, '.git', 'HEAD'), 'ref: refs/heads/outro\n')
    expect(readGitHeadCached(root)).toEqual({ branch: 'outro', commit: H3.slice(0, 40) })
  })

  it('`unsupported` e `null` não ficam em cache', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    expect(readGitHeadCached(root)).toBeNull()
    write('.git/refs/heads/main', `${H1}\n`)
    expect(readGitHeadCached(root)).toEqual({ branch: 'main', commit: H1 })
  })

  it('packed-refs que muda invalida o cache', () => {
    write('.git/HEAD', 'ref: refs/heads/main\n')
    const packed = write('.git/packed-refs', `${H1} refs/heads/main\n`)
    const a = readGitHeadCached(root)
    fs.writeFileSync(packed, `${H2} refs/heads/main\n`)
    const t = Date.now() / 1000 + 5
    fs.utimesSync(packed, t, t)
    expect(readGitHeadCached(root)).toEqual({ branch: 'main', commit: H2 })
    expect(a).toEqual({ branch: 'main', commit: H1 })
  })
})

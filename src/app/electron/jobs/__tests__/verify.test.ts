import { describe, expect, it } from 'vitest'
import { parseProjectToml, verifyAddProject, verifyJob, type VerifyDeps } from '../verify'
import type { HubProject } from '../../data/types'
import type { ResolvedJob } from '../catalog'

function hub(over: Partial<HubProject> = {}): HubProject {
  return {
    id: 'x',
    name: 'outro',
    path: 'C:\\projetos\\outro',
    cloned: true,
    embeddingModel: null,
    visibility: 'workspace',
    status: 'ok',
    chunks: 0,
    lastSync: null,
    ...over,
  }
}

function deps(over: Partial<VerifyDeps> = {}): VerifyDeps {
  return {
    readRegistry: () => [],
    readFile: () => null,
    platform: 'win32',
    ...over,
  }
}

const PREFIX = 'O projeto foi indexado, mas não entrou no painel'

describe('verifyAddProject', () => {
  it('pasta registrada no hub: sem erro (comparação sem maiúsculas e barras no Windows)', () => {
    const d = deps({ readRegistry: () => [hub({ name: 'novo', path: 'C:\\Projetos\\Novo' })] })
    expect(verifyAddProject('c:/projetos/novo/', d)).toBeNull()
  })

  it('fora do Windows, letra diferente é outra pasta', () => {
    const d = deps({ platform: 'linux', readRegistry: () => [hub({ name: 'novo', path: '/home/me/Novo' })] })
    expect(verifyAddProject('/home/me/novo', d)).not.toBeNull()
    expect(verifyAddProject('/home/me/Novo', d)).toBeNull()
  })

  it('colisão de nome no hub: explica e diz como resolver', () => {
    const d = deps({
      readRegistry: () => [hub({ name: 'src', path: 'C:\\a\\src' })],
      readFile: (p) => (p.replace(/\\/g, '/').endsWith('C:/b/src/ragx.toml') ? '[project]\nname = "src"\nid = "1"\n' : null),
    })
    expect(verifyAddProject('C:/b/src', d)).toBe(
      `${PREFIX}: já existe um projeto com o nome src no hub. Renomeie em ragx.toml ([project] name) e adicione de novo.`,
    )
  })

  it('projeto privado: explica que private nunca entra no hub', () => {
    const d = deps({
      readFile: () => '[project]\nname = "segredo"\nvisibility = "private"\n',
    })
    expect(verifyAddProject('C:/b/segredo', d)).toBe(
      `${PREFIX} porque está marcado como privado (visibility = "private").`,
    )
  })

  it('sem motivo conhecido: manda rodar o registro na mão para ver o erro', () => {
    const d = deps({ readFile: () => '[project]\nname = "x"\n' })
    expect(verifyAddProject('C:/b/x', d)).toBe(
      `${PREFIX}: o registro no hub falhou. Rode "ragx project register" nessa pasta para ver o motivo.`,
    )
  })

  it('registry ilegível (escrita concorrente): não culpa a tarefa', () => {
    const d = deps({
      readRegistry: () => {
        throw new Error('json truncado')
      },
    })
    expect(verifyAddProject('C:/b/x', d)).toBeNull()
  })
})

describe('parseProjectToml', () => {
  it('lê name e visibility só da seção [project], com comentários e aspas simples', () => {
    const text = [
      '# config',
      'name = "fora"',
      '[project]',
      "name = 'meu projeto' # comentário",
      'visibility="private"',
      '',
      '[security]',
      'visibility = "workspace"',
    ].join('\r\n')
    expect(parseProjectToml(text)).toEqual({ name: 'meu projeto', visibility: 'private' })
  })

  it('escapes simples em aspas duplas', () => {
    expect(parseProjectToml('[project]\nname = "a \\"b\\" c"\n')).toEqual({ name: 'a "b" c', visibility: null })
  })

  it('sem seção [project]: tudo null', () => {
    expect(parseProjectToml('[index]\nmax_file_bytes = 1\n')).toEqual({ name: null, visibility: null })
  })
})

describe('verifyJob', () => {
  const addJob: ResolvedJob = {
    kind: 'add-project',
    label: 'Adicionar x',
    projectId: null,
    steps: [],
    dedupeKey: 'add-project|C:/b/x',
    model: null,
    folder: 'C:/b/x',
  }

  it('só confere add-project', () => {
    const d = deps()
    expect(verifyJob(addJob, d)).not.toBeNull()
    expect(verifyJob({ ...addJob, kind: 'update', folder: undefined }, d)).toBeNull()
  })
})

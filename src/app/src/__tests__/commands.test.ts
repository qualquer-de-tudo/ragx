import { describe, expect, it } from 'vitest'
import { MAX_RESULTS, PALETTE_JOB_KINDS, buildCommands, filterCommands } from '../commands'
import { shortcutFor } from '../shortcuts'
import { snap } from '../test/snap'

const projects = [
  snap({ id: 'juriflux', name: 'Juriflux', path: 'C:/p/juriflux' }),
  snap({ id: 'sp', name: 'São Paulo', path: 'C:/p/sp', counts: { documents: 3, chunks: 10, embeddings: 4, pendingEmbeddings: 6 } }),
  snap({ id: 'gone', name: 'Sumido', path: 'C:/p/gone', exists: false, counts: { documents: 3, chunks: 10, embeddings: 4, pendingEmbeddings: 6 } }),
]

describe('buildCommands', () => {
  const all = buildCommands(projects)
  const label = (c: { label: string }) => c.label

  it('páginas, abrir, atualizar, embeddings só onde faltam, verificar e refazer', () => {
    const labels = all.map(label)
    expect(labels).toEqual(expect.arrayContaining(['Ir para Projetos', 'Ir para Atividade', 'Ir para Conexões', 'Ir para Como funciona']))
    expect(labels).toEqual(expect.arrayContaining(['Abrir Juriflux', 'Atualizar Juriflux', 'Verificar conexões agora', 'Refazer a configuração inicial']))
    expect(labels).toContain('Gerar embeddings em São Paulo')
    expect(labels).not.toContain('Gerar embeddings em Juriflux') // nada faltando
  })

  it('projeto sem pasta fica desabilitado (atualizar e embeddings)', () => {
    expect(all.find((c) => c.id === 'update:gone')!.disabled).toBe(true)
    expect(all.find((c) => c.id === 'embed:gone')!.disabled).toBe(true)
    expect(all.find((c) => c.id === 'update:juriflux')!.disabled).toBeFalsy()
  })

  it('PROPRIEDADE: a paleta só enfileira kind da lista fechada', () => {
    expect([...PALETTE_JOB_KINDS]).toEqual(['update', 'embed'])
    for (const c of all) {
      if (c.action.type === 'job') {
        expect(PALETTE_JOB_KINDS as readonly string[]).toContain(c.action.kind)
        expect(Object.keys(c.action).sort()).toEqual(['kind', 'projectId', 'type'])
      }
    }
  })
})

describe('filterCommands', () => {
  const all = buildCommands(projects)

  it('ignora acento e caixa', () => {
    expect(filterCommands(all, 'sao paulo').map((c) => c.label)).toContain('Abrir São Paulo')
    expect(filterCommands(all, 'JUR').map((c) => c.label)).toContain('Abrir Juriflux')
  })

  it('quem começa pelo texto vem antes de quem só o contém', () => {
    const out = filterCommands(all, 'at').map((c) => c.label)
    // "Atualizar ..." e "Atividade" começam por "at"; "Ir para Atividade" começa numa palavra; "Refazer a ..." só contém
    const firstContains = out.findIndex((l) => !l.toLowerCase().split(/\s+/).some((w) => w.startsWith('at')))
    const lastPrefix = out.map((l) => l.toLowerCase().split(/\s+/).some((w) => w.startsWith('at'))).lastIndexOf(true)
    if (firstContains !== -1) expect(lastPrefix).toBeLessThan(firstContains)
  })

  it('no máximo 8 resultados, e sem texto devolve os primeiros', () => {
    const many = buildCommands(Array.from({ length: 30 }, (_, i) => snap({ id: `p${i}`, name: `Proj ${i}` })))
    expect(filterCommands(many, 'proj')).toHaveLength(MAX_RESULTS)
    expect(filterCommands(many, '')).toHaveLength(MAX_RESULTS)
    expect(filterCommands(all, 'zzzz')).toEqual([])
  })
})

describe('shortcutFor', () => {
  const key = (k: string, over: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) => ({
    key: k, ctrlKey: false, metaKey: false, altKey: false, ...over,
  })

  it('Ctrl e Cmd + K abrem a paleta, mesmo em campo de texto', () => {
    expect(shortcutFor(key('k', { ctrlKey: true }), true)).toEqual({ type: 'palette' })
    expect(shortcutFor(key('K', { metaKey: true }), false)).toEqual({ type: 'palette' })
  })

  it('/ e ? só fora de campo', () => {
    expect(shortcutFor(key('/'), false)).toEqual({ type: 'search' })
    expect(shortcutFor(key('?'), false)).toEqual({ type: 'help' })
    expect(shortcutFor(key('/'), true)).toBeNull()
    expect(shortcutFor(key('?'), true)).toBeNull()
  })

  it('Ctrl 1..4 navegam; Alt nunca', () => {
    expect(shortcutFor(key('2', { ctrlKey: true }), false)).toEqual({ type: 'go', route: { page: 'activity' } })
    expect(shortcutFor(key('5', { ctrlKey: true }), false)).toBeNull()
    expect(shortcutFor(key('k', { ctrlKey: true, altKey: true }), false)).toBeNull()
    expect(shortcutFor(key('1', { altKey: true }), false)).toBeNull()
  })
})

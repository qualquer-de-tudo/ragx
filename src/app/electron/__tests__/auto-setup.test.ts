import { describe, expect, it, vi } from 'vitest'
import { createAutoSetup, RETRY_MS, type AutoSetupState, type HealResult, type LocalProject } from '../auto-setup'

function make(
  over: {
    enabled?: boolean
    heal?: () => Promise<HealResult>
    projects?: LocalProject[]
    install?: (id: string) => boolean
  } = {},
) {
  let clock = 1_000_000
  const states: AutoSetupState[] = []
  const projects = { list: over.projects ?? [] }
  const install = vi.fn(over.install ?? (() => true))
  const heal = vi.fn(over.heal ?? (async () => ({ healed: [] })))
  const setup = createAutoSetup({
    enabled: () => over.enabled ?? true,
    healClaude: heal,
    projects: () => projects.list,
    installGitHooks: install,
    onState: (s) => states.push(s),
    now: () => clock,
  })
  return { setup, heal, install, states, projects, advance: (ms: number) => (clock += ms) }
}

describe('ajuste automático', () => {
  it('desligado: não toca no Claude nem nos projetos', async () => {
    const t = make({ enabled: false, projects: [{ id: 'a', name: 'a', hooksInstalled: false }] })
    const s = await t.setup.run()
    expect(s.enabled).toBe(false)
    expect(t.heal).not.toHaveBeenCalled()
    expect(t.install).not.toHaveBeenCalled()
  })

  it('conta e descreve em português o que o heal instalou', async () => {
    const t = make({
      heal: async () => ({
        healed: [
          { name: 'empresa', installed: ['touch', 'nudge'], skipped: [], failed: [] },
          { name: 'padrão', installed: [], skipped: [], failed: [] },
        ],
      }),
    })
    const s = await t.setup.run()
    expect(s.claude).toEqual({ checked: 2, installed: ['empresa: aviso de edição, lembrete de busca'], error: null })
    expect(s.lastRunAt).not.toBeNull()
  })

  it('perfil que não aceitou a instalação vira erro legível', async () => {
    const t = make({ heal: async () => ({ healed: [{ name: 'vitor', installed: [], skipped: [], failed: ['touch'] }] }) })
    const s = await t.setup.run()
    expect(s.claude.error).toBe('Não consegui instalar: vitor: aviso de edição')
  })

  it('o ragx fora do ar não derruba a rodada: o erro fica no estado e os projetos seguem', async () => {
    const t = make({
      heal: async () => {
        throw new Error('Comando não encontrado: ragx')
      },
      projects: [{ id: 'a', name: 'alfa', hooksInstalled: false }],
    })
    const s = await t.setup.run()
    expect(s.claude.error).toBe('Comando não encontrado: ragx')
    expect(s.git.queued).toEqual(['alfa'])
  })

  it('enfileira os hooks de git só de quem está explicitamente sem eles', async () => {
    const t = make({
      projects: [
        { id: 'a', name: 'alfa', hooksInstalled: false },
        { id: 'b', name: 'beta', hooksInstalled: true },
        { id: 'c', name: 'gama', hooksInstalled: null },
      ],
    })
    const s = await t.setup.run()
    expect(t.install).toHaveBeenCalledTimes(1)
    expect(t.install).toHaveBeenCalledWith('a')
    expect(s.git).toEqual({ queued: ['alfa'], failed: [] })
  })

  it('projeto recusado pela fila aparece em failed', async () => {
    const t = make({ projects: [{ id: 'a', name: 'alfa', hooksInstalled: false }], install: () => false })
    expect((await t.setup.run()).git).toEqual({ queued: [], failed: ['alfa'] })
  })

  it('não tenta o mesmo projeto de novo antes de RETRY_MS, mesmo com o status ainda sem hooks', async () => {
    const t = make({ projects: [{ id: 'a', name: 'alfa', hooksInstalled: false }] })
    await t.setup.run()
    t.advance(RETRY_MS - 1)
    await t.setup.run()
    expect(t.install).toHaveBeenCalledTimes(1)
    t.advance(2)
    await t.setup.run()
    expect(t.install).toHaveBeenCalledTimes(2)
  })

  it('duas chamadas juntas viram uma rodada só', async () => {
    const t = make()
    await Promise.all([t.setup.run(), t.setup.run()])
    expect(t.heal).toHaveBeenCalledTimes(1)
  })

  describe('onSnapshot', () => {
    it('roda quando há projeto sem hooks de git ainda não tentado', async () => {
      const t = make({ projects: [{ id: 'a', name: 'alfa', hooksInstalled: false }] })
      t.setup.onSnapshot()
      await vi.waitFor(() => expect(t.install).toHaveBeenCalledTimes(1))
    })

    it('não roda quando está tudo em dia, nem a cada snapshot para quem já foi tentado', async () => {
      const t = make({ projects: [{ id: 'a', name: 'alfa', hooksInstalled: true }] })
      t.setup.onSnapshot()
      expect(t.heal).not.toHaveBeenCalled()

      t.projects.list = [{ id: 'a', name: 'alfa', hooksInstalled: false }]
      await t.setup.run()
      t.setup.onSnapshot()
      t.setup.onSnapshot()
      expect(t.heal).toHaveBeenCalledTimes(1)
    })

    it('desligado: não roda', () => {
      const t = make({ enabled: false, projects: [{ id: 'a', name: 'alfa', hooksInstalled: false }] })
      t.setup.onSnapshot()
      expect(t.heal).not.toHaveBeenCalled()
    })
  })
})

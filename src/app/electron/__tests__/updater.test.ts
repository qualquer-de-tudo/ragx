import { describe, expect, it, vi } from 'vitest'
import { createUpdater, type UpdateState, type UpdaterLike } from '../updater'

function fakeAutoUpdater() {
  const handlers = new Map<string, (...a: never[]) => void>()
  const u = {
    autoDownload: true,
    autoInstallOnAppQuit: true,
    channel: null as string | null,
    allowPrerelease: false,
    checkForUpdates: vi.fn(async () => undefined),
    downloadUpdate: vi.fn(async () => undefined),
    quitAndInstall: vi.fn(),
    on: vi.fn((event: string, fn: (...a: never[]) => void) => void handlers.set(event, fn)),
  }
  const emit = (event: string, ...args: unknown[]) => (handlers.get(event) as (...a: unknown[]) => void)(...args)
  return { u: u as UpdaterLike & typeof u, emit }
}

function make(over: { isPackaged?: boolean; enabled?: boolean; version?: string } = {}) {
  const f = fakeAutoUpdater()
  const states: UpdateState[] = []
  const updater = createUpdater({
    autoUpdater: f.u,
    isPackaged: over.isPackaged ?? true,
    version: over.version ?? '1.0.0',
    enabled: () => over.enabled ?? true,
    onState: (s) => states.push(s),
  })
  updater.init()
  return { ...f, updater, states }
}

describe('createUpdater', () => {
  it('init: autoDownload e autoInstallOnAppQuit falsos, canal latest', () => {
    const { u } = make()
    expect(u.autoDownload).toBe(false)
    expect(u.autoInstallOnAppQuit).toBe(false)
    expect(u.channel).toBe('latest')
  })

  it('allowPrerelease só com versão -beta', () => {
    expect(make({ version: '1.0.0-beta.5' }).u.allowPrerelease).toBe(true)
    expect(make({ version: '1.0.0' }).u.allowPrerelease).toBe(false)
  })

  it('desligado (padrão): ZERO chamadas de rede, mesmo pedindo para verificar', async () => {
    const { u, updater } = make({ enabled: false })
    await updater.check()
    await updater.download()
    expect(u.checkForUpdates).not.toHaveBeenCalled()
    expect(u.downloadUpdate).not.toHaveBeenCalled()
    expect(updater.getState().status).toBe('idle')
  })

  it('painel não empacotado (dev): zero chamadas mesmo ligado', async () => {
    const { u, updater } = make({ isPackaged: false, enabled: true })
    await updater.check()
    expect(u.checkForUpdates).not.toHaveBeenCalled()
  })

  it('verificar passa por checking e "available" NÃO baixa sozinho', async () => {
    const { u, updater, emit, states } = make()
    await updater.check()
    expect(u.checkForUpdates).toHaveBeenCalledTimes(1)
    expect(states.map((s) => s.status)).toContain('checking')
    emit('update-available', { version: '1.1.0' })
    expect(updater.getState()).toMatchObject({ status: 'available', version: '1.1.0' })
    expect(u.downloadUpdate).not.toHaveBeenCalled()
  })

  it('baixar só depois de available; mostra progresso e termina em downloaded', async () => {
    const { u, updater, emit } = make()
    await updater.download() // sem available: ignorado
    expect(u.downloadUpdate).not.toHaveBeenCalled()
    emit('update-available', { version: '1.1.0' })
    await updater.download()
    expect(u.downloadUpdate).toHaveBeenCalledTimes(1)
    emit('download-progress', { percent: 42.4 })
    expect(updater.getState()).toMatchObject({ status: 'downloading', progress: 42 })
    emit('update-downloaded', { version: '1.1.0' })
    expect(updater.getState()).toMatchObject({ status: 'downloaded', progress: 100 })
  })

  it('instalar fora de downloaded é recusado; em downloaded chama quitAndInstall', () => {
    const { u, updater, emit } = make()
    expect(() => updater.install()).toThrow(/pedido recusado/)
    emit('update-available', { version: '1.1.0' })
    expect(() => updater.install()).toThrow(/pedido recusado/)
    emit('update-downloaded', { version: '1.1.0' })
    updater.install()
    expect(u.quitAndInstall).toHaveBeenCalledTimes(1)
    // silencioso e reabrindo o painel (o instalador é assistido; sem isto abriria o assistente)
    expect(u.quitAndInstall).toHaveBeenCalledWith(true, true)
  })

  it('sem atualização volta a idle', async () => {
    const { updater, emit } = make()
    emit('update-available', { version: '1.1.0' })
    emit('update-not-available')
    expect(updater.getState()).toMatchObject({ status: 'idle', version: null })
  })

  it('erro de rede vira error com mensagem em português e não lança', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { u, updater } = make()
    u.checkForUpdates.mockRejectedValueOnce(new Error('getaddrinfo ENOTFOUND github.com'))
    const s = await updater.check()
    expect(s.status).toBe('error')
    expect(s.error).toMatch(/servidor de atualizações/)
    expect(s.error).not.toContain('github.com')
  })

  it('erro de integridade explica o descarte; evento error também vira estado', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { updater, emit } = make()
    emit('error', new Error('sha512 checksum mismatch'))
    expect(updater.getState()).toMatchObject({ status: 'error', error: expect.stringContaining('integridade') })
  })

  it('não verifica de novo enquanto já verifica ou baixa', async () => {
    const { u, updater } = make()
    const p = updater.check()
    await updater.check() // segunda enquanto a primeira está checking
    await p
    expect(u.checkForUpdates).toHaveBeenCalledTimes(1)
  })
})

import { useEffect, useState } from 'react'
import type { UpdateState } from '../types/ragx-bridge'
import { Section } from '../components/shell/Card'
import { Segmented } from '../components/ui/Segmented'
import { currentTheme, setTheme, type ThemePref } from '../theme'
import { Switch } from '../components/ui/Switch'
import { ipcErrorMessage } from '../ipcError'
import { notify } from '../toast'

type Prefs = { tray: boolean; notifyStale: boolean; autoUpdate: boolean }
type Key = keyof Prefs

/**
 * Preferências do painel. As tarefas 0191, 0192 e 0193 compartilham esta página: cada uma acrescenta uma seção.
 * "Bandeja e avisos" (RAGX-0191): ícone na bandeja com o estado geral e notificação quando um índice continua
 * defasado. Os dois entram DESLIGADOS: aviso mal calibrado irrita mais do que ajuda.
 */
export function PreferencesPage() {
  const [prefs, setPrefs] = useState<Prefs | null>(null)
  const [update, setUpdate] = useState<UpdateState | null>(null)
  const [theme, setThemeState] = useState<ThemePref>(currentTheme)

  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => window.ragx.getSettings())
      .then(
        (s) => {
          if (!cancelled) setPrefs({ tray: s.tray === true, notifyStale: s.notifyStale === true, autoUpdate: s.autoUpdate !== false })
        },
        (err: unknown) => {
          console.error('getSettings() falhou:', err)
          if (!cancelled) setPrefs({ tray: false, notifyStale: false, autoUpdate: false })
        },
      )
    return () => {
      cancelled = true
    }
  }, [])

  // Estado da atualização (RAGX-0192): lê no mount e acompanha o evento do processo principal.
  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => window.ragx.getUpdateState())
      .then(
        (u) => {
          if (!cancelled) setUpdate(u)
        },
        (err: unknown) => console.error('getUpdateState() falhou:', err),
      )
    const off = window.ragx.onUpdate((u) => setUpdate(u))
    return () => {
      cancelled = true
      off()
    }
  }, [])

  const updateAction = (run: () => Promise<UpdateState | void>) => {
    run().then(
      (u) => {
        if (u) setUpdate(u)
      },
      (err: unknown) => {
        console.error('ação de atualização falhou:', err)
        notify.error(`Não foi possível atualizar: ${ipcErrorMessage(err)}`)
      },
    )
  }

  const changeTheme = (next: ThemePref) => {
    const before = theme
    setThemeState(next) // troca na hora, sem reiniciar
    setTheme(next).catch((err: unknown) => {
      console.error('setTheme() falhou:', err)
      setThemeState(before)
      void setTheme(before, false)
      notify.error(`Não foi possível salvar o tema: ${ipcErrorMessage(err)}`)
    })
  }

  const change = (key: Key, value: boolean) => {
    window.ragx.setPreference(key, value).then(
      () => setPrefs((p) => (p ? { ...p, [key]: value } : p)),
      (err: unknown) => {
        console.error('setPreference() falhou:', err)
        notify.error(`Não foi possível salvar a preferência: ${ipcErrorMessage(err)}`)
      },
    )
  }

  return (
    <section className="page">
      <header className="page-head">
        <h1 className="page-title">Preferências</h1>
      </header>
      <Section title="Aparência">
        <div className="pref-row">
          <div>
            <p className="pref-title" id="pref-theme">
              Tema
            </p>
            <p className="hint">Escuro é o padrão. "Seguir o sistema" acompanha o modo claro ou escuro do Windows.</p>
          </div>
          <Segmented
            label="Tema"
            value={theme}
            options={[
              { value: 'dark', label: 'Escuro' },
              { value: 'light', label: 'Claro' },
              { value: 'system', label: 'Seguir o sistema' },
            ]}
            onChange={changeTheme}
          />
        </div>
      </Section>
      <Section title="Bandeja e avisos">
        <div className="pref-row">
          <div>
            <p className="pref-title" id="pref-tray">
              Ícone na bandeja do sistema
            </p>
            <p className="hint">Mostra o estado geral ao passar o mouse (por exemplo, "2 defasados") e abre o painel com um clique.</p>
          </div>
          <Switch checked={prefs?.tray === true} labelledBy="pref-tray" disabled={prefs === null} onChange={(v) => change('tray', v)} />
        </div>
        <div className="pref-row">
          <div>
            <p className="pref-title" id="pref-notify">
              Avisar quando um índice ficar defasado
            </p>
            <p className="hint">
              Uma notificação do sistema, uma vez por projeto, só se o índice continuar defasado por mais de 2 minutos (depois de
              um commit com hook o índice fica defasado por alguns segundos, e isso não avisa). Com esta opção ligada e a janela
              fora da vista, o painel confere os projetos uma vez por minuto, sem abrir processos.
            </p>
          </div>
          <Switch
            checked={prefs?.notifyStale === true}
            labelledBy="pref-notify"
            disabled={prefs === null}
            onChange={(v) => change('notifyStale', v)}
          />
        </div>
      </Section>
      <Section title="Atualizações">
        <div className="pref-row">
          <div>
            <p className="pref-title" id="pref-update">
              Verificar atualizações do painel
            </p>
            <p className="hint">
              Ligado por padrão: confere o GitHub Releases ao abrir e quando você pede, e só baixa e instala quando você
              manda. Desligado, o painel não faz nenhuma chamada de rede.
            </p>
          </div>
          <Switch
            checked={prefs?.autoUpdate === true}
            labelledBy="pref-update"
            disabled={prefs === null}
            onChange={(v) => change('autoUpdate', v)}
          />
        </div>
        <p className="hint" role="note">
          O instalador não é assinado: o Windows pode mostrar o aviso do SmartScreen ao atualizar. A integridade do arquivo
          baixado é conferida pelo hash do <code>latest.yml</code>.
        </p>
        <p className="update-status" role="status">
          Versão atual: {update?.currentVersion ?? '…'}
          {update?.status === 'checking' && ' · verificando…'}
          {update?.status === 'available' && ` · versão ${update.version ?? 'nova'} disponível`}
          {update?.status === 'downloading' && ` · baixando${update.progress !== null ? ` (${update.progress}%)` : ''}…`}
          {update?.status === 'downloaded' && ` · versão ${update.version ?? 'nova'} baixada, pronta para instalar`}
          {update?.status === 'error' && ` · ${update.error ?? 'erro ao atualizar'}`}
        </p>
        <div className="pricing-actions">
          <button
            type="button"
            className="btn"
            disabled={prefs?.autoUpdate !== true || update?.status === 'checking' || update?.status === 'downloading'}
            onClick={() => updateAction(() => window.ragx.checkForUpdates())}
          >
            Verificar agora
          </button>
          {update?.status === 'available' && (
            <button type="button" className="btn" onClick={() => updateAction(() => window.ragx.downloadUpdate())}>
              Baixar atualização
            </button>
          )}
          {update?.status === 'downloaded' && (
            <button type="button" className="btn btn-primary" onClick={() => updateAction(() => window.ragx.installUpdate())}>
              Instalar e reiniciar
            </button>
          )}
        </div>
      </Section>
    </section>
  )
}

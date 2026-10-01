import { useEffect, useState } from 'react'
import { Section } from '../components/shell/Card'
import { Switch } from '../components/ui/Switch'
import { ipcErrorMessage } from '../ipcError'
import { notify } from '../toast'

type Prefs = { tray: boolean; notifyStale: boolean }
type Key = keyof Prefs

/**
 * Preferências do painel. As tarefas 0191, 0192 e 0193 compartilham esta página: cada uma acrescenta uma seção.
 * "Bandeja e avisos" (RAGX-0191): ícone na bandeja com o estado geral e notificação quando um índice continua
 * defasado. Os dois entram DESLIGADOS: aviso mal calibrado irrita mais do que ajuda.
 */
export function PreferencesPage() {
  const [prefs, setPrefs] = useState<Prefs | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => window.ragx.getSettings())
      .then(
        (s) => {
          if (!cancelled) setPrefs({ tray: s.tray === true, notifyStale: s.notifyStale === true })
        },
        (err: unknown) => {
          console.error('getSettings() falhou:', err)
          if (!cancelled) setPrefs({ tray: false, notifyStale: false })
        },
      )
    return () => {
      cancelled = true
    }
  }, [])

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
    </section>
  )
}

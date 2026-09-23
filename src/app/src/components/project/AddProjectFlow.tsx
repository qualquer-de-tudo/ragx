import { useEffect, useRef, useState } from 'react'
import type { DiscoverItem } from '../../types/ragx-bridge'

const TRUNCATED_NOTE =
  'Busca parcial: a pasta é grande demais para varrer inteira. Escolha uma pasta mais específica se faltar algum projeto.'

type Found =
  | { status: 'idle' }
  | { status: 'searching' }
  | { status: 'failed' }
  | { status: 'done'; items: DiscoverItem[]; truncated: boolean }

function lastSegment(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean)
  return parts[parts.length - 1] ?? path
}

function addLabel(n: number): string {
  return n === 1 ? 'Adicionar 1 projeto' : `Adicionar ${n} projetos`
}

/**
 * Corpo do "Adicionar projeto": escolher pasta, ver os projetos do RAGX
 * dentro dela, marcar quais entram e enfileirar um `add-project` por item.
 * Fica separado do diálogo para o onboarding reaproveitar (Task 10).
 *
 * Tudo que volta ao processo principal é token: o caminho só aparece na tela.
 */
export function AddProjectFlow({ onDone, onCancel }: { onDone: () => void; onCancel?: () => void }) {
  const [folder, setFolder] = useState<{ token: string; path: string } | null>(null)
  const [found, setFound] = useState<Found>({ status: 'idle' })
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [installHooks, setInstallHooks] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [failed, setFailed] = useState<string[]>([])

  // Descarta respostas de uma escolha de pasta anterior (ou chegadas depois
  // de o diálogo fechar).
  const request = useRef(0)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  async function choose() {
    let picked: { token: string; path: string } | null
    try {
      picked = await window.ragx.pickFolder()
    } catch (err) {
      console.error('pickFolder() falhou:', err)
      return
    }
    if (picked === null || !alive.current) return

    const mine = ++request.current
    setFolder(picked)
    setFound({ status: 'searching' })
    setSelected(new Set())
    setFailed([])
    try {
      const result = await window.ragx.discover(picked.token)
      if (!alive.current || request.current !== mine) return
      setFound({ status: 'done', items: result.items, truncated: result.truncated })
      setSelected(new Set(result.items.filter((i) => !i.alreadyRegistered).map((i) => i.token)))
    } catch (err) {
      if (!alive.current || request.current !== mine) return
      console.error('discover() falhou:', err)
      setFound({ status: 'failed' })
    }
  }

  function toggle(token: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(token)) next.delete(token)
      else next.add(token)
      return next
    })
  }

  // Nome para a mensagem de erro de cada token marcável.
  const names = new Map<string, string>()
  if (folder) names.set(folder.token, lastSegment(folder.path))
  if (found.status === 'done') for (const i of found.items) names.set(i.token, i.name)

  async function submit() {
    setSubmitting(true)
    setFailed([])
    const notAdded: string[] = []
    // Um por vez, na ordem da lista: a fila é serial de qualquer jeito.
    for (const token of selected) {
      try {
        await window.ragx.enqueueJob({ kind: 'add-project', folderToken: token, installHooks })
      } catch (err) {
        console.error('enqueueJob(add-project) falhou:', err)
        notAdded.push(token)
      }
    }
    if (!alive.current) return
    setSubmitting(false)
    if (notAdded.length === 0) {
      onDone()
      return
    }
    // O que entrou na fila sai da seleção; o que falhou fica para tentar de novo.
    setSelected(new Set(notAdded))
    setFailed(notAdded.map((t) => names.get(t) ?? t))
  }

  const count = selected.size

  return (
    <div className="add-flow">
      <div className="add-flow-pick">
        <button type="button" className="btn" data-autofocus onClick={() => void choose()} disabled={submitting}>
          Escolher pasta
        </button>
        {folder && <p className="mono add-flow-path">{folder.path}</p>}
      </div>

      {found.status === 'searching' && (
        <p className="dim" role="status">
          Procurando projetos…
        </p>
      )}

      {found.status === 'failed' && (
        <p className="callout callout-error" role="alert">
          Não foi possível procurar projetos nesta pasta.
        </p>
      )}

      {found.status === 'done' && folder && (
        <fieldset className="add-flow-found">
          <legend className="add-flow-legend">
            {found.items.length === 0 ? 'Nenhum projeto do RAGX nesta pasta' : 'Projetos encontrados'}
          </legend>
          <ul className="add-flow-list">
            {found.items.length === 0 ? (
              <li>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={selected.has(folder.token)}
                    onChange={() => toggle(folder.token)}
                  />
                  <span>Usar esta pasta como um projeto novo</span>
                </label>
              </li>
            ) : (
              found.items.map((item) => (
                <li key={item.token}>
                  <label className={`check${item.alreadyRegistered ? ' is-disabled' : ''}`}>
                    <input
                      type="checkbox"
                      checked={!item.alreadyRegistered && selected.has(item.token)}
                      disabled={item.alreadyRegistered}
                      onChange={() => toggle(item.token)}
                    />
                    <span className="check-body">
                      <span className="check-name">{item.name}</span>{' '}
                      <span className="mono dim">{item.path}</span>{' '}
                      {item.alreadyRegistered && <span className="hint">já está no painel</span>}
                    </span>
                  </label>
                </li>
              ))
            )}
          </ul>
          {found.truncated && <p className="hint add-flow-note">{TRUNCATED_NOTE}</p>}
        </fieldset>
      )}

      {folder && (
        <label className="check">
          <input type="checkbox" checked={installHooks} onChange={(e) => setInstallHooks(e.target.checked)} />
          <span>Instalar hooks de git (mantém o índice na branch em que você está)</span>
        </label>
      )}

      {failed.length > 0 && (
        <p className="callout callout-error" role="alert">
          Não foi possível adicionar {failed.join(', ')}.
        </p>
      )}

      <div className="add-flow-actions">
        {onCancel && (
          <button type="button" className="btn btn-quiet" onClick={onCancel}>
            Cancelar
          </button>
        )}
        <button
          type="button"
          className="btn btn-primary"
          disabled={count === 0 || submitting}
          onClick={() => void submit()}
        >
          {addLabel(count)}
        </button>
      </div>
    </div>
  )
}

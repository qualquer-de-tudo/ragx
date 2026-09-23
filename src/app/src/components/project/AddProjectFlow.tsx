import { useEffect, useMemo, useRef, useState } from 'react'
import type { DiscoverItem } from '../../types/ragx-bridge'

const TRUNCATED_NOTE =
  'Busca parcial: a pasta é grande demais para varrer inteira. Escolha uma pasta mais específica se faltar algum projeto.'

type Search = 'idle' | 'searching' | 'failed' | 'done'

/** Item da lista: o que `discover` achou, ou a própria pasta escolhida quando ela não tinha nada dentro. */
interface Candidate extends DiscoverItem {
  /** A própria pasta escolhida, oferecida porque a busca nela não achou nada. */
  ownFolder: boolean
}

function lastSegment(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean)
  return parts[parts.length - 1] ?? path
}

/** Chave para não repetir a mesma pasta vinda de duas escolhas (cada `discover` emite tokens novos). */
function pathKey(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+$/, '')
}

function addLabel(n: number): string {
  return n === 1 ? 'Adicionar 1 projeto' : `Adicionar ${n} projetos`
}

/** Projeto do RAGX já existente começa marcado; repositório novo e a própria pasta, não. */
function startsChecked(c: Candidate): boolean {
  return !c.ownFolder && !c.isNew && !c.alreadyRegistered
}

/** Projeto marcado: o token vai para o `add-project`; o nome é só para a tela. */
export interface PickedProject {
  token: string
  name: string
}

/**
 * Corpo do "Adicionar projeto": escolher pastas, ver os projetos do RAGX e
 * os repositórios git (sem `ragx.toml`, marcados "novo") dentro delas, marcar
 * quais entram e enfileirar um `add-project` por item. Cada "Escolher pasta"
 * soma à lista (sem repetir a mesma pasta), e cada item pode sair dela.
 * Fica separado do diálogo para o onboarding reaproveitar.
 *
 * Dois modos:
 * - diálogo (`onDone`): tem os próprios botões e enfileira ao confirmar;
 * - embutido (`onSelectionChange`, passo 3 do onboarding): sem botões, avisa
 *   a seleção a cada mudança e quem enfileira é o passo 4. O checkbox de hooks
 *   pode ser controlado de fora (`installHooks`/`onInstallHooksChange`).
 *
 * Tudo que volta ao processo principal é token: o caminho só aparece na tela.
 */
export function AddProjectFlow({
  onDone,
  onCancel,
  onSelectionChange,
  installHooks: hooksProp,
  onInstallHooksChange,
}: {
  onDone?: () => void
  onCancel?: () => void
  onSelectionChange?: (picked: PickedProject[]) => void
  installHooks?: boolean
  onInstallHooksChange?: (value: boolean) => void
}) {
  const [lastFolder, setLastFolder] = useState<{ token: string; path: string } | null>(null)
  const [search, setSearch] = useState<Search>('idle')
  const [lastFoundNothing, setLastFoundNothing] = useState(false)
  const [truncated, setTruncated] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  // Espelho de `candidates` para somar a lista sem depender de um fechamento velho.
  const candidatesRef = useRef<Candidate[]>([])
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [ownHooks, setOwnHooks] = useState(true)
  const installHooks = hooksProp ?? ownHooks
  const setInstallHooks = onInstallHooksChange ?? setOwnHooks
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

  function commitCandidates(next: Candidate[]) {
    candidatesRef.current = next
    setCandidates(next)
  }

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
    setLastFolder(picked)
    setSearch('searching')
    setLastFoundNothing(false)
    setTruncated(false)
    setFailed([])
    try {
      const result = await window.ragx.discover(picked.token)
      if (!alive.current || request.current !== mine) return
      const found: Candidate[] =
        result.items.length > 0
          ? result.items.map((i) => ({ ...i, ownFolder: false }))
          : [
              {
                token: picked.token,
                path: picked.path,
                name: lastSegment(picked.path),
                alreadyRegistered: false,
                isNew: true,
                ownFolder: true,
              },
            ]
      const current = candidatesRef.current
      const known = new Set(current.map((c) => pathKey(c.path)))
      const added = found.filter((c) => !known.has(pathKey(c.path)))
      commitCandidates([...current, ...added])
      setSelected((prev) => new Set([...prev, ...added.filter(startsChecked).map((c) => c.token)]))
      setSearch('done')
      setLastFoundNothing(result.items.length === 0)
      setTruncated(result.truncated)
    } catch (err) {
      if (!alive.current || request.current !== mine) return
      console.error('discover() falhou:', err)
      setSearch('failed')
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

  function remove(token: string) {
    commitCandidates(candidatesRef.current.filter((c) => c.token !== token))
    setSelected((prev) => {
      const next = new Set(prev)
      next.delete(token)
      return next
    })
  }

  // Seleção na ordem da lista (a mesma em que o diálogo enfileira).
  const picked = useMemo<PickedProject[]>(
    () =>
      candidates
        .filter((c) => !c.alreadyRegistered && selected.has(c.token))
        .map((c) => ({ token: c.token, name: c.name })),
    [candidates, selected],
  )

  useEffect(() => {
    onSelectionChange?.(picked)
  }, [picked, onSelectionChange])

  async function submit() {
    setSubmitting(true)
    setFailed([])
    const notAdded: PickedProject[] = []
    // Um por vez, na ordem da lista: a fila é serial de qualquer jeito.
    for (const p of picked) {
      try {
        await window.ragx.enqueueJob({ kind: 'add-project', folderToken: p.token, installHooks })
      } catch (err) {
        console.error('enqueueJob(add-project) falhou:', err)
        notAdded.push(p)
      }
    }
    if (!alive.current) return
    setSubmitting(false)
    if (notAdded.length === 0) {
      onDone?.()
      return
    }
    // O que entrou na fila sai da seleção; o que falhou fica para tentar de novo.
    setSelected(new Set(notAdded.map((p) => p.token)))
    setFailed(notAdded.map((p) => p.name))
  }

  const count = picked.length

  return (
    <div className="add-flow">
      <div className="add-flow-pick">
        <button type="button" className="btn" data-autofocus onClick={() => void choose()} disabled={submitting}>
          Escolher pasta
        </button>
        {lastFolder && <p className="mono add-flow-path">{lastFolder.path}</p>}
      </div>

      {search === 'searching' && (
        <p className="dim" role="status">
          Procurando projetos…
        </p>
      )}

      {search === 'failed' && (
        <p className="callout callout-error" role="alert">
          Não foi possível procurar projetos nesta pasta.
        </p>
      )}

      {search === 'done' && lastFoundNothing && (
        <p className="hint">Nenhum projeto do RAGX nem repositório git nesta pasta.</p>
      )}

      {candidates.length > 0 && (
        <fieldset className="add-flow-found">
          <legend className="add-flow-legend">Projetos encontrados</legend>
          <ul className="add-flow-list">
            {candidates.map((c) => (
              <li key={c.token} className="add-flow-item">
                <label className={`check${c.alreadyRegistered ? ' is-disabled' : ''}`}>
                  <input
                    type="checkbox"
                    checked={!c.alreadyRegistered && selected.has(c.token)}
                    disabled={c.alreadyRegistered}
                    onChange={() => toggle(c.token)}
                  />
                  <span className="check-body">
                    <span className="check-name">{c.ownFolder ? 'Usar esta pasta como um projeto novo' : c.name}</span>{' '}
                    <span className="mono dim">{c.path}</span>{' '}
                    {c.isNew && <span className="badge badge-accent">novo</span>}
                    {c.alreadyRegistered && <span className="hint">já está no painel</span>}
                  </span>
                </label>
                <button
                  type="button"
                  className="btn btn-quiet btn-sm add-flow-remove"
                  aria-label={`Remover ${c.name} da lista`}
                  onClick={() => remove(c.token)}
                  disabled={submitting}
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
          <p className="hint add-flow-note">
            Escolha outra pasta para somar mais projetos. Os marcados como novo ganham um ragx.toml ao serem adicionados.
          </p>
          {truncated && <p className="hint add-flow-note">{TRUNCATED_NOTE}</p>}
        </fieldset>
      )}

      {lastFolder && (
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

      {!onSelectionChange && (
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
      )}
    </div>
  )
}

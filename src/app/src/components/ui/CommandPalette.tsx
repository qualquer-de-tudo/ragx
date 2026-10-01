import { useId, useMemo, useState, type KeyboardEvent } from 'react'
import type { Command } from '../../commands'
import { filterCommands } from '../../commands'
import { SHORTCUTS } from '../../shortcuts'
import { Modal } from './Modal'

/**
 * Paleta de comandos (Ctrl+K, RAGX-0183) sobre o `Modal`: padrão combobox com lista (`role="listbox"`). Setas movem a
 * opção ativa (com volta ao fim), Enter executa, Esc fecha e devolve o foco (o `Modal` cuida). A contagem de
 * resultados vai para uma região `aria-live` em `sr-only`. Só procura em memória (páginas, projetos e ações).
 */
export function CommandPalette({
  commands,
  onRun,
  onClose,
}: {
  commands: readonly Command[]
  onRun: (command: Command) => void
  onClose: () => void
}) {
  const listId = useId()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const results = useMemo(() => filterCommands(commands, query), [commands, query])
  const current = results.length === 0 ? -1 : Math.min(active, results.length - 1)
  const optionId = (i: number) => `${listId}-opt-${i}`

  const run = (c: Command) => {
    if (c.disabled) return
    onRun(c)
    onClose()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (results.length === 0) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((current + step + results.length) % results.length)
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault()
      setActive(e.key === 'Home' ? 0 : Math.max(results.length - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (current >= 0) run(results[current])
    }
  }

  return (
    <Modal title="Paleta de comandos" onClose={onClose}>
      <div className="palette">
        <input
          type="text"
          className="search-input palette-input"
          role="combobox"
          aria-label="Buscar comando"
          aria-autocomplete="list"
          aria-expanded={results.length > 0}
          aria-controls={listId}
          aria-activedescendant={current >= 0 ? optionId(current) : undefined}
          placeholder="Digite para buscar páginas, projetos e ações"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onKeyDown={onKeyDown}
          spellCheck={false}
          autoComplete="off"
          data-autofocus
        />
        <ul id={listId} role="listbox" aria-label="Comandos" className="palette-list">
          {results.map((c, i) => (
            <li
              key={c.id}
              id={optionId(i)}
              role="option"
              aria-selected={i === current}
              aria-disabled={c.disabled || undefined}
              className={`palette-item${i === current ? ' is-active' : ''}${c.disabled ? ' is-disabled' : ''}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => run(c)}
            >
              <span className="palette-label">{c.label}</span>
              {c.hint && <span className="palette-hint dim">{c.hint}</span>}
            </li>
          ))}
        </ul>
        {results.length === 0 && <p className="dim palette-empty">Nenhum comando para essa busca.</p>}
        <p role="status" aria-live="polite" className="sr-only">
          {results.length === 0 ? 'Nenhum resultado' : results.length === 1 ? '1 resultado' : `${results.length} resultados`}
        </p>
      </div>
    </Modal>
  )
}

export function ShortcutsHelp({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Atalhos de teclado" onClose={onClose}>
      <dl className="shortcuts">
        {SHORTCUTS.map((s) => (
          <div key={s.keys} className="shortcut-row">
            <dt>
              {s.keys.split(' ').map((k, i) => (
                <kbd key={i}>{k}</kbd>
              ))}
            </dt>
            <dd>{s.what}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  )
}

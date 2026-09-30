import { useRef, type KeyboardEvent, type ReactNode } from 'react'

export interface TabItem<T extends string> {
  id: T
  label: string
}

/**
 * Abas no padrão WAI-ARIA: setas trocam de aba, Home/End vão às pontas, e só a
 * aba ativa entra na ordem do Tab. Os painéis ficam por conta de `TabPanel`,
 * que mantém os inativos montados: trocar de aba não perde estado (a página
 * carregada da linha do tempo, a simulação em andamento).
 */
export function Tabs<T extends string>({
  label,
  tabs,
  active,
  onChange,
  idPrefix,
}: {
  label: string
  tabs: readonly TabItem<T>[]
  active: T
  onChange: (id: T) => void
  idPrefix: string
}) {
  const refs = useRef(new Map<T, HTMLButtonElement>())

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const i = tabs.findIndex((t) => t.id === active)
    const alvo =
      event.key === 'ArrowRight'
        ? tabs[(i + 1) % tabs.length]
        : event.key === 'ArrowLeft'
          ? tabs[(i - 1 + tabs.length) % tabs.length]
          : event.key === 'Home'
            ? tabs[0]
            : event.key === 'End'
              ? tabs[tabs.length - 1]
              : undefined
    if (!alvo) return
    event.preventDefault()
    onChange(alvo.id)
    refs.current.get(alvo.id)?.focus()
  }

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((t) => {
        const selected = t.id === active
        return (
          <button
            key={t.id}
            ref={(el) => {
              if (el) refs.current.set(t.id, el)
              else refs.current.delete(t.id)
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${t.id}`}
            tabIndex={selected ? 0 : -1}
            className={`tab${selected ? ' tab-active' : ''}`}
            onClick={() => onChange(t.id)}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

export function TabPanel({
  id,
  idPrefix,
  active,
  children,
}: {
  id: string
  idPrefix: string
  active: boolean
  children: ReactNode
}) {
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-tab-${id}`}
      hidden={!active}
      className="tab-panel"
    >
      {children}
    </div>
  )
}

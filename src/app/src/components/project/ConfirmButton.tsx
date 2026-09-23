import { useEffect, useState } from 'react'

const ARMED_MS = 5000

/**
 * Botão de ação destrutiva sem janela de confirmação: o primeiro clique troca
 * o texto para `confirmLabel` por 5 s; um segundo clique nesse intervalo
 * confirma. Esc, ou o prazo passar, volta ao normal.
 */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  tone = 'neutral',
  disabled = false,
  ariaLabel,
}: {
  label: string
  confirmLabel: string
  onConfirm: () => void
  /** `critical`: a confirmação aparece em vermelho. */
  tone?: 'neutral' | 'critical'
  disabled?: boolean
  /** Nome acessível quando o texto visível não basta (ex.: "Na fila"). */
  ariaLabel?: string
}) {
  const [armed, setArmed] = useState(false)
  // Desabilitado no meio da confirmação (ex.: a tarefa entrou na fila por
  // outro caminho): desarma, para não voltar armado depois.
  if (disabled && armed) setArmed(false)
  const active = armed && !disabled

  useEffect(() => {
    if (!active) return
    const timer = setTimeout(() => setArmed(false), ARMED_MS)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setArmed(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('keydown', onKey)
    }
  }, [active])

  const onClick = () => {
    if (disabled) return
    if (!active) {
      setArmed(true)
      return
    }
    setArmed(false)
    onConfirm()
  }

  const cls = ['btn', active ? (tone === 'critical' ? 'btn-danger' : 'btn-primary') : tone === 'critical' ? 'btn-danger-quiet' : '']
    .filter(Boolean)
    .join(' ')

  return (
    <>
      <button
        type="button"
        className={cls}
        onClick={onClick}
        disabled={disabled}
        aria-label={active ? undefined : ariaLabel}
      >
        {active ? confirmLabel : label}
      </button>
      <span className="sr-only" role="status">
        {active ? 'Clique de novo para confirmar.' : ''}
      </span>
    </>
  )
}

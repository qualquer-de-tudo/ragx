import type { ButtonHTMLAttributes, ReactNode } from 'react'

/** O trilho e o polegar do interruptor da barra superior (o `.switch-track` do App.css). */
export function SwitchTrack() {
  return (
    <span className="switch-track" aria-hidden="true">
      <span className="switch-thumb" />
    </span>
  )
}

type Name = { label: string; labelledBy?: never } | { labelledBy: string; label?: never }

/**
 * Interruptor (`role="switch"`) isolado, o `.switch` de 38x22. Exige nome acessível, por `label` ou `labelledBy`.
 * Clique, Espaço e Enter chamam `onChange` com o valor novo (é um `<button>`).
 */
export function Switch({
  checked,
  onChange,
  disabled = false,
  label,
  labelledBy,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
} & Name) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-label={label}
      aria-labelledby={labelledBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-knob" aria-hidden="true" />
    </button>
  )
}

/**
 * Interruptor composto da barra superior: o botão inteiro é o `role="switch"` e leva o trilho mais o texto de estado
 * (`children`). `className` põe o visual do botão; o resto dos atributos de `<button>` passa direto.
 */
export function SwitchButton({
  checked,
  children,
  ...rest
}: { checked: boolean; children: ReactNode } & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'role' | 'type' | 'aria-checked'>) {
  return (
    <button type="button" role="switch" aria-checked={checked} {...rest}>
      {children}
    </button>
  )
}

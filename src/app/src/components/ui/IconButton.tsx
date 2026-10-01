import { Icon } from './Icon'
import type { IconName } from './icons'

/**
 * Botão só de ícone. `label` é obrigatório no tipo (vira `aria-label`): sem ele o botão não compila, porque um botão
 * sem texto visível não tem nome para o leitor de tela.
 */
export function IconButton({
  label,
  icon,
  onClick,
  className = '',
}: {
  label: string
  icon: IconName
  onClick: () => void
  /** Classe extra (a base é `btn btn-quiet btn-icon`). */
  className?: string
}) {
  return (
    <button type="button" className={`btn btn-quiet btn-icon${className ? ` ${className}` : ''}`} aria-label={label} onClick={onClick}>
      <Icon name={icon} />
    </button>
  )
}

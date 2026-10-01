import { dismiss, pause, resume, useToasts } from '../../toast'
import { IconButton } from './IconButton'

/**
 * Os avisos da tela (RAGX-0180). A região viva fica SEMPRE no DOM, antes do primeiro aviso: o leitor de tela só anuncia
 * o que entra numa região que já existe. Sucesso é `role="status"`, erro é `role="alert"`. O prazo pausa com o ponteiro
 * ou o foco em cima, e "Fechar" tira na hora. Montado uma vez em `App`.
 */
export function Toaster() {
  const toasts = useToasts()
  return (
    <div className="toaster" aria-live="polite" aria-label="Avisos" role="region">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast-${t.kind}`}
          role={t.kind === 'error' ? 'alert' : 'status'}
          onMouseEnter={() => pause(t.id)}
          onMouseLeave={() => resume(t.id)}
          onFocus={() => pause(t.id)}
          onBlur={() => resume(t.id)}
        >
          <p className="toast-text">{t.text}</p>
          <IconButton label="Fechar aviso" icon="close" onClick={() => dismiss(t.id)} />
        </div>
      ))}
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'

export interface ClaudeToggle {
  /** `null` enquanto não se sabe o estado (ou se a leitura falhou). */
  enabled: boolean | null
  busy: boolean
  error: string | null
  /** Houve uma troca nesta sessão do painel: o Claude Code só a vê na próxima sessão dele. */
  changed: boolean
  toggle: () => void
}

/**
 * Interruptor global do RAGX no Claude Code. O estado vem da CLI (`ragx claude
 * status`), nunca de um valor guardado aqui: quem editou `~/.claude.json` por
 * fora é visto na próxima leitura. Ao ligar/desligar, o botão só muda quando a
 * CLI confirma - falha deixa o estado como estava e mostra o motivo.
 */
export function useClaudeIntegration(): ClaudeToggle {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [changed, setChanged] = useState(false)
  const alive = useRef(true)
  const inFlight = useRef(false)

  useEffect(() => {
    alive.current = true
    window.ragx.getClaudeIntegration().then(
      (s) => {
        if (alive.current) setEnabled(s.enabled)
      },
      (err: unknown) => {
        console.error('getClaudeIntegration() falhou:', err)
        if (alive.current) setError('Não consegui ler o estado do Claude Code.')
      },
    )
    return () => {
      alive.current = false
    }
  }, [])

  const toggle = useCallback(() => {
    if (enabled === null || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    window.ragx.setClaudeIntegration(!enabled).then(
      (s) => {
        inFlight.current = false
        if (!alive.current) return
        setEnabled(s.enabled)
        setChanged(true)
        setBusy(false)
      },
      (err: unknown) => {
        inFlight.current = false
        console.error('setClaudeIntegration() falhou:', err)
        if (!alive.current) return
        setError(err instanceof Error ? err.message : 'Não consegui alterar o Claude Code.')
        setBusy(false)
      },
    )
  }, [enabled])

  return { enabled, busy, error, changed, toggle }
}

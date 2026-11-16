import { useCallback, useEffect, useRef, useState } from 'react'
import type { UsageReport } from '../types/ragx-bridge'
import { ipcErrorMessage } from '../ipcError'

/** O último relatório desta janela: voltar a uma página mostra os números na hora, sem "Lendo…". */
let lastReport: UsageReport | null = null

/** Só para testes: esquece o relatório guardado. */
export function forgetUsage(): void {
  lastReport = null
}

export interface UsageState {
  report: UsageReport | null
  loading: boolean
  error: string | null
  /** "Atualizar": pede uma leitura nova (o processo principal limita a uma por minuto). */
  refresh: () => void
}

/**
 * Consumo real (RAGX-0205), de `ragx usage --json`. Pede no mount; o processo principal devolve o resultado guardado
 * (até 10 min) sem abrir processo. Falha vira `error`, e a tela segue com o que tinha.
 */
export function useUsage(): UsageState {
  const [report, setReport] = useState<UsageReport | null>(lastReport)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const seq = useRef(0)

  // Só muda estado na resposta (nunca direto no efeito): o "carregando" do mount já é o estado inicial.
  const load = useCallback((force: boolean) => {
    const id = ++seq.current
    Promise.resolve()
      .then(() => window.ragx.getUsage(force))
      .then(
        (r) => {
          if (id !== seq.current) return
          lastReport = r
          setReport(r)
          setError(null)
          setLoading(false)
        },
        (err: unknown) => {
          if (id !== seq.current) return
          setError(ipcErrorMessage(err))
          setLoading(false)
        },
      )
  }, [])

  useEffect(() => {
    load(false)
    return () => {
      seq.current += 1 // desmontou: a resposta que chegar depois é descartada
    }
  }, [load])

  const refresh = useCallback(() => {
    setLoading(true)
    load(true)
  }, [load])
  return { report, loading, error, refresh }
}

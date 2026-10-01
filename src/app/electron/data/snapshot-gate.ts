import type { Snapshot } from '../../src/types/ragx-bridge'

/**
 * Porteiro do `ragx:snapshot` (RAGX-0175): diz se o snapshot muda o que o renderer já tem. O processo principal
 * reconstrói o snapshot a cada 5 s e ele sempre sai com `generatedAt` novo; sem diferença no resto do conteúdo,
 * mandar de novo é só IPC e render à toa. `latestSnapshot` e o handler `getSnapshot` seguem atualizados fora daqui.
 */
export function createSnapshotGate(): { shouldSend: (snapshot: Snapshot) => boolean; reset: () => void } {
  let last: string | null = null
  const fingerprint = (s: Snapshot): string => JSON.stringify({ ...s, generatedAt: null })
  return {
    shouldSend(snapshot) {
      const now = fingerprint(snapshot)
      if (now === last) return false
      last = now
      return true
    },
    /** A janela foi recriada: o renderer novo não viu nada, o próximo snapshot sai de qualquer jeito. */
    reset() {
      last = null
    },
  }
}

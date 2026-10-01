/**
 * O motivo de uma rejeição de IPC, sem o prefixo que o Electron põe nas rejeições de `invoke`
 * (`Error invoking remote method 'ragx:enqueueJob': Error: <motivo>`). Mensagem sem prefixo passa intacta, e o que
 * não é `Error` vira texto.
 */
export function ipcErrorMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err)
  return raw.replace(/^Error invoking remote method '[^']*':\s*(?:Error:\s*)?/, '').trim() || 'erro desconhecido'
}

/** Quem disparou a indexação (`index_runs.source`). */
const SOURCE_LABEL: Record<string, string> = {
  cli: 'Terminal',
  panel: 'Painel',
  watch: 'Watcher',
  sync: 'Sync',
  'mcp:refresh': 'Agente (refresh)',
  'mcp:index': 'Agente (reindex)',
  'hook:post-checkout': 'Troca de branch',
  'hook:post-commit': 'Commit',
  'hook:post-merge': 'Merge ou pull',
}

/** Quem disparou uma indexação, em português (`hook:post-commit` → "Commit"). */
export function sourceLabel(source: string | null): string {
  if (source === null) return 'sem dados'
  return Object.hasOwn(SOURCE_LABEL, source) ? SOURCE_LABEL[source] : source
}

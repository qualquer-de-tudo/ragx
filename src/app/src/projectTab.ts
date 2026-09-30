export type ProjectTab = 'geral' | 'economia' | 'historico' | 'manutencao'

// A aba escolhida vale para o próximo projeto aberto, enquanto o painel estiver
// aberto (como o cache de trial e scan em onDemandCache.ts).
let last: ProjectTab = 'geral'

export function lastProjectTab(): ProjectTab {
  return last
}

export function rememberProjectTab(tab: ProjectTab): void {
  last = tab
}

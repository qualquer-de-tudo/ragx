/** Página que o painel mostra. Estado em memória: não há URL nem histórico. */
export type Route =
  | { page: 'projects' }
  | { page: 'project'; id: string }
  | { page: 'activity' }
  | { page: 'connections' }
  | { page: 'how' }
  | { page: 'preferences' }
  | { page: 'onboarding' }

/** Item da barra lateral que fica ativo para cada rota (`null`: nenhum). */
export function navSection(route: Route): 'projects' | 'activity' | 'connections' | 'how' | 'preferences' | null {
  switch (route.page) {
    case 'projects':
    case 'project':
      return 'projects'
    case 'activity':
      return 'activity'
    case 'connections':
      return 'connections'
    case 'how':
      return 'how'
    case 'preferences':
      return 'preferences'
    default:
      return null
  }
}

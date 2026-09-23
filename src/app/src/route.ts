/** Página que o painel mostra. Estado em memória: não há URL nem histórico. */
export type Route =
  | { page: 'projects' }
  | { page: 'project'; id: string }
  | { page: 'connections' }
  | { page: 'how' }
  | { page: 'onboarding' }

/** Item da barra lateral que fica ativo para cada rota (`null`: nenhum). */
export function navSection(route: Route): 'projects' | 'connections' | 'how' | null {
  switch (route.page) {
    case 'projects':
    case 'project':
      return 'projects'
    case 'connections':
      return 'connections'
    case 'how':
      return 'how'
    default:
      return null
  }
}

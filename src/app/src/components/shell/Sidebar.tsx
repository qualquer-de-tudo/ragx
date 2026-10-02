import { navSection, type Route } from '../../route'
import { RagxMark } from '../brand/RagxMark'
import { Icon } from '../ui/Icon'
import type { IconName } from '../ui/icons'

type Section = 'projects' | 'activity' | 'connections' | 'how' | 'preferences'

type Item = { section: Section; label: string; route: Route; icon: IconName }

const ITEMS: Item[] = [
  { section: 'projects', label: 'Projetos', route: { page: 'projects' }, icon: 'projects' },
  { section: 'activity', label: 'Atividade', route: { page: 'activity' }, icon: 'activity' },
  { section: 'connections', label: 'Conexões', route: { page: 'connections' }, icon: 'connections' },
  { section: 'preferences', label: 'Preferências', route: { page: 'preferences' }, icon: 'preferences' },
]

/** Ajuda fica no fim da barra, longe do que se usa todo dia. */
const FOOT_ITEMS: Item[] = [{ section: 'how', label: 'Como funciona', route: { page: 'how' }, icon: 'how' }]

export function Sidebar({
  route,
  onNavigate,
  live = false,
  updateAvailable = false,
}: {
  route: Route
  onNavigate: (route: Route) => void
  /** Algum projeto teve atividade no último minuto: acende o ponto de "Atividade". */
  live?: boolean
  /** Há versão nova do painel: acende um ponto em Preferências, onde está o botão de baixar. */
  updateAvailable?: boolean
}) {
  const active = navSection(route)
  const item = (it: Item) => (
    <li key={it.section}>
      <button
        type="button"
        className="nav-item"
        aria-current={active === it.section ? 'page' : undefined}
        onClick={() => onNavigate(it.route)}
      >
        <Icon name={it.icon} size={20} strokeWidth={1.6} className="nav-icon" />
        <span className="nav-label">{it.label}</span>
        {it.section === 'activity' && live && (
          <span className="live-dot live-dot-on nav-live" role="img" aria-label="em uso agora" />
        )}
        {it.section === 'preferences' && updateAvailable && (
          <span className="nav-update-dot" role="img" aria-label="atualização disponível" />
        )}
      </button>
    </li>
  )
  return (
    <aside className="sidebar">
      <div className="brand" aria-hidden="true">
        <RagxMark size={26} />
        <span className="brand-name">RAGX</span>
      </div>
      <nav className="nav" aria-label="Principal">
        <ul>{ITEMS.map(item)}</ul>
        <ul className="nav-foot">{FOOT_ITEMS.map(item)}</ul>
      </nav>
    </aside>
  )
}

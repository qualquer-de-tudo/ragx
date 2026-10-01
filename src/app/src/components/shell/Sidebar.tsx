import { navSection, type Route } from '../../route'
import { RagxMark } from '../brand/RagxMark'
import { Icon } from '../ui/Icon'
import type { IconName } from '../ui/icons'

type Section = 'projects' | 'activity' | 'connections' | 'how' | 'preferences'

const ITEMS: Array<{ section: Section; label: string; route: Route; icon: IconName }> = [
  { section: 'projects', label: 'Projetos', route: { page: 'projects' }, icon: 'projects' },
  { section: 'activity', label: 'Atividade', route: { page: 'activity' }, icon: 'activity' },
  { section: 'connections', label: 'Conexões', route: { page: 'connections' }, icon: 'connections' },
  { section: 'how', label: 'Como funciona', route: { page: 'how' }, icon: 'how' },
  { section: 'preferences', label: 'Preferências', route: { page: 'preferences' }, icon: 'preferences' },
]

export function Sidebar({
  route,
  onNavigate,
  live = false,
}: {
  route: Route
  onNavigate: (route: Route) => void
  /** Algum projeto teve atividade no último minuto: acende o ponto de "Atividade". */
  live?: boolean
}) {
  const active = navSection(route)
  return (
    <aside className="sidebar">
      <div className="brand" aria-hidden="true">
        <RagxMark size={26} />
        <span className="brand-name">RAGX</span>
      </div>
      <nav className="nav" aria-label="Principal">
        <ul>
          {ITEMS.map((item) => (
            <li key={item.section}>
              <button
                type="button"
                className="nav-item"
                aria-current={active === item.section ? 'page' : undefined}
                onClick={() => onNavigate(item.route)}
              >
                <Icon name={item.icon} size={20} strokeWidth={1.6} className="nav-icon" />
                <span className="nav-label">{item.label}</span>
                {item.section === 'activity' && live && (
                  <span className="live-dot live-dot-on nav-live" role="img" aria-label="em uso agora" />
                )}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}

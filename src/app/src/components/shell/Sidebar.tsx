import type { ReactNode } from 'react'
import { navSection, type Route } from '../../route'

type Section = 'projects' | 'connections' | 'how'

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="nav-icon"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

const ITEMS: Array<{ section: Section; label: string; route: Route; icon: ReactNode }> = [
  {
    section: 'projects',
    label: 'Projetos',
    route: { page: 'projects' },
    icon: (
      <Icon>
        <rect x="4" y="4" width="7" height="7" rx="1.5" />
        <rect x="13" y="4" width="7" height="7" rx="1.5" />
        <rect x="4" y="13" width="7" height="7" rx="1.5" />
        <rect x="13" y="13" width="7" height="7" rx="1.5" />
      </Icon>
    ),
  },
  {
    section: 'connections',
    label: 'Conexões',
    route: { page: 'connections' },
    icon: (
      <Icon>
        <circle cx="6" cy="12" r="2.5" />
        <circle cx="18" cy="6" r="2.5" />
        <circle cx="18" cy="18" r="2.5" />
        <path d="M8.2 10.8 15.8 7.2M8.2 13.2l7.6 3.6" />
      </Icon>
    ),
  },
  {
    section: 'how',
    label: 'Como funciona',
    route: { page: 'how' },
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M9.6 9.6a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.6" />
        <path d="M12 16.9v.1" />
      </Icon>
    ),
  },
]

export function Sidebar({ route, onNavigate }: { route: Route; onNavigate: (route: Route) => void }) {
  const active = navSection(route)
  return (
    <aside className="sidebar">
      <div className="brand" aria-hidden="true">
        RAGX
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
                {item.icon}
                <span className="nav-label">{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}

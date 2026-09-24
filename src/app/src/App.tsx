import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSnapshot } from './hooks/useSnapshot'
import { useJobs } from './hooks/useJobs'
import { useConnections } from './hooks/useConnections'
import { useClaudeIntegration } from './hooks/useClaudeIntegration'
import { Sidebar } from './components/shell/Sidebar'
import { TopBar, type Health } from './components/shell/TopBar'
import type { Route } from './route'
import type { ConnectionCheck } from './types/ragx-bridge'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { HowItWorksPage } from './pages/HowItWorksPage'
import { Onboarding } from './pages/Onboarding'
import { ProjectsPage } from './pages/ProjectsPage'
import { ProjectPage } from './pages/ProjectPage'
import './App.css'

export type { Route } from './route'

const byName = (a: { name: string }, b: { name: string }) =>
  a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' })

const RANK = { ok: 0, warn: 1, error: 2 } as const

function worstOf(checks: ConnectionCheck[] | null): Health {
  if (!checks || checks.length === 0) return null
  return checks.reduce<ConnectionCheck['state']>((w, c) => (RANK[c.state] > RANK[w] ? c.state : w), 'ok')
}

function App() {
  const { snapshot } = useSnapshot()
  const jobs = useJobs()
  // Depois de uma correção de conexão, quem confere de novo é o processo
  // principal (o resultado chega por `ragx:connections`).
  const { connections, checking, refresh } = useConnections()
  const claude = useClaudeIntegration()

  // `null` enquanto não se sabe. Uma falha ao ler as preferências não prende
  // ninguém no onboarding.
  const [onboardingDone, setOnboardingDone] = useState<boolean | null>(null)
  const [route, setRoute] = useState<Route | null>(null)
  const [query, setQuery] = useState('')
  const contentRef = useRef<HTMLElement>(null)

  useEffect(() => {
    let cancelled = false
    window.ragx.getSettings().then(
      (s) => {
        if (!cancelled) setOnboardingDone(s.onboardingDone)
      },
      (err) => {
        console.error('getSettings() falhou:', err)
        if (!cancelled) setOnboardingDone(true)
      },
    )
    return () => {
      cancelled = true
    }
  }, [])

  // Chave da rota para fins de scroll: página, mais o projeto quando houver.
  const routeScrollKey = route === null ? null : route.page === 'project' ? `project:${route.id}` : route.page

  // Toda troca de rota recomeça pelo topo: sem isso, abrir um projeto depois
  // de rolar Projetos até o fim abre a página de detalhe já rolada para
  // baixo.
  useEffect(() => {
    const el = contentRef.current
    if (el) el.scrollTop = 0
  }, [routeScrollKey])

  // Rota inicial: decidida uma vez só, quando há dado para isso (preferências
  // e, se o onboarding já foi feito, o primeiro snapshot). Depois disso só o
  // usuário muda a rota: um snapshot novo não arranca ninguém do onboarding.
  // (Ajuste de estado durante o render, com guarda: padrão documentado do React.)
  if (route === null) {
    if (onboardingDone === false) setRoute({ page: 'onboarding' })
    else if (onboardingDone === true && snapshot !== null)
      setRoute(snapshot.projects.length === 0 ? { page: 'onboarding' } : { page: 'projects' })
  }

  const projects = useMemo(() => [...(snapshot?.projects ?? [])].sort(byName), [snapshot])
  // O processo principal guarda o resultado da última checagem no snapshot;
  // enquanto ele não tem, vale a checagem feita daqui.
  const health: Health = snapshot?.connectionsHealth ?? worstOf(connections)

  const onQuery = useCallback((q: string) => {
    setQuery(q)
    // A busca é de projetos: digitar em outra página leva à lista.
    setRoute((r) => (r && r.page !== 'projects' && r.page !== 'onboarding' ? { page: 'projects' } : r))
  }, [])

  const onCancelJob = useCallback((id: string) => {
    window.ragx.cancelJob(id).catch((err: unknown) => console.error('cancelJob() falhou:', err))
  }, [])

  // O próprio onboarding grava a preferência; aqui só se sai dele.
  const finishOnboarding = useCallback(() => {
    setOnboardingDone(true)
    setRoute({ page: 'projects' })
  }, [])

  if (route === null) {
    return (
      <div className="boot" role="status">
        Carregando…
      </div>
    )
  }

  // Onboarding é tela cheia, sem barra lateral nem barra superior.
  if (route.page === 'onboarding') {
    return (
      <Onboarding
        connections={connections}
        checking={checking}
        onRefresh={() => void refresh()}
        jobs={jobs}
        onFinish={finishOnboarding}
      />
    )
  }

  let page
  switch (route.page) {
    case 'projects':
      page = (
        <ProjectsPage
          projects={projects}
          jobs={jobs}
          query={query}
          onOpen={(id) => setRoute({ page: 'project', id })}
        />
      )
      break
    case 'project':
      page = (
        <ProjectPage
          key={route.id}
          project={projects.find((p) => p.id === route.id) ?? null}
          jobs={jobs}
          onBack={() => setRoute({ page: 'projects' })}
        />
      )
      break
    case 'connections':
      page = (
        <ConnectionsPage connections={connections} checking={checking} onRefresh={() => void refresh()} jobs={jobs} />
      )
      break
    case 'how':
      page = <HowItWorksPage onRestart={() => setRoute({ page: 'onboarding' })} />
      break
  }

  return (
    <div className="shell">
      <Sidebar route={route} onNavigate={setRoute} />
      <div className="shell-main">
        <TopBar
          query={query}
          onQuery={onQuery}
          jobs={jobs}
          health={health}
          claude={claude}
          onOpenConnections={() => setRoute({ page: 'connections' })}
          onCancelJob={onCancelJob}
        />
        <main className="content" ref={contentRef}>
          <div className="content-inner">{page}</div>
        </main>
      </div>
    </div>
  )
}

export default App

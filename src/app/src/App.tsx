import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSnapshot } from './hooks/useSnapshot'
import { useJobs } from './hooks/useJobs'
import { useConnections } from './hooks/useConnections'
import { useClaudeIntegration } from './hooks/useClaudeIntegration'
import { hasNewVersion, useUpdate } from './hooks/useUpdate'
import { useActivity } from './hooks/useActivity'
import { useJobFailureToasts } from './hooks/useJobFailureToasts'
import { ipcErrorMessage } from './ipcError'
import { notify } from './toast'
import { Toaster } from './components/ui/Toaster'
import { SkeletonCard, SkeletonRegion } from './components/ui/Skeleton'
import { CommandPalette, ShortcutsHelp } from './components/ui/CommandPalette'
import { useShortcuts } from './hooks/useShortcuts'
import { buildCommands, type Command } from './commands'
import { enqueue } from './jobs'
import type { ShortcutAction } from './shortcuts'
import { formatClock } from './format'
import { useLiveIds } from './hooks/useClock'
import { ActivityPage } from './pages/ActivityPage'
import { Sidebar } from './components/shell/Sidebar'
import { TopBar, type Health } from './components/shell/TopBar'
import type { Route } from './route'
import type { ConnectionCheck } from './types/ragx-bridge'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { HowItWorksPage } from './pages/HowItWorksPage'
import { PreferencesPage } from './pages/PreferencesPage'
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
  return checks.filter((c) => c.id !== 'claude').reduce<ConnectionCheck['state']>((w, c) => (RANK[c.state] > RANK[w] ? c.state : w), 'ok')
}

function App() {
  const { snapshot, fromCache, error: snapshotError, retry } = useSnapshot()
  const jobs = useJobs()
  useJobFailureToasts(jobs)
  // Depois de uma correção de conexão, quem confere de novo é o processo
  // principal (o resultado chega por `ragx:connections`).
  const { connections, checking, refresh } = useConnections()
  const claude = useClaudeIntegration()
  const update = useUpdate()
  const updateReady = hasNewVersion(update)
  const activity = useActivity()
  // "Em uso agora" apaga um minuto depois do último evento, sem evento novo. O `Set` só muda quando a pertença muda,
  // então o App não renderiza a cada tick do relógio.
  const liveIds = useLiveIds(activity)

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

  const openProject = useCallback((id: string) => setRoute({ page: 'project', id }), [])

  // Paleta de comandos e ajuda de atalhos (RAGX-0183).
  const [overlay, setOverlay] = useState<'palette' | 'help' | null>(null)
  const commands = useMemo(() => buildCommands(projects), [projects])
  const runCommand = useCallback(
    (c: Command) => {
      const a = c.action
      if (a.type === 'route') setRoute(a.route)
      else if (a.type === 'job') void enqueue(a.kind, a.projectId).then((j) => j && notify.success(`Adicionado à fila: ${c.label}`))
      else void refresh()
    },
    [refresh],
  )
  const onShortcut = useCallback(
    (a: ShortcutAction) => {
      if (a.type === 'palette') setOverlay((o) => (o === 'palette' ? null : 'palette'))
      else if (overlay !== null) return // com uma janela aberta só o Ctrl+K age (para fechar)
      else if (a.type === 'help') setOverlay('help')
      else if (a.type === 'search') document.getElementById('topbar-search')?.focus()
      else setRoute(a.route)
    },
    [overlay],
  )
  useShortcuts(route !== null && route.page !== 'onboarding', onShortcut)

  // O clique numa notificação do sistema (RAGX-0191) pede o detalhe de um projeto; só o `projectId` chega.
  useEffect(() => window.ragx.onOpenProject((id) => setRoute({ page: 'project', id })), [])

  // O clique na notificação de versão nova leva às Preferências, onde ficam "Baixar" e "Instalar e reiniciar".
  useEffect(() => window.ragx.onOpenPreferences(() => setRoute({ page: 'preferences' })), [])

  // Com o painel à vista a notificação do sistema passa batida: um aviso na tela, uma vez por versão.
  const avisada = useRef<string | null>(null)
  const novaVersao = update?.status === 'available' ? update.version : null
  useEffect(() => {
    if (novaVersao === null || novaVersao === avisada.current) return
    avisada.current = novaVersao
    notify.info(`RAGX ${novaVersao} disponível. Baixe em Preferências.`)
  }, [novaVersao])

  const onCancelJob = useCallback((id: string) => {
    window.ragx.cancelJob(id).catch((err: unknown) => {
      console.error('cancelJob() falhou:', err)
      notify.error(`Não foi possível cancelar a tarefa: ${ipcErrorMessage(err)}`)
    })
  }, [])

  // O próprio onboarding grava a preferência; aqui só se sai dele.
  const finishOnboarding = useCallback(() => {
    setOnboardingDone(true)
    setRoute({ page: 'projects' })
  }, [])

  // Só as preferências ainda são desconhecidas: fundo vazio, sem "Carregando…" em tela cheia e sem piscar a casca
  // antes do onboarding (RAGX-0182).
  if (route === null && onboardingDone !== true) return <div className="boot" />

  // Onboarding é tela cheia, sem barra lateral nem barra superior.
  if (route !== null && route.page === 'onboarding') {
    return (
      <>
        <Onboarding
          connections={connections}
          checking={checking}
          onRefresh={() => void refresh()}
          jobs={jobs}
          onFinish={finishOnboarding}
          claude={claude}
        />
        <Toaster />
      </>
    )
  }

  // Preferências lidas e nenhum snapshot ainda: a casca já aparece, com skeleton (ou o erro) no conteúdo.
  const shellRoute: Route = route ?? { page: 'projects' }
  let page
  switch (shellRoute.page) {
    case 'projects':
      page = (
        <ProjectsPage
          projects={projects}
          jobs={jobs}
          query={query}
          liveIds={liveIds}
          onOpen={openProject}
        />
      )
      break
    case 'activity':
      page = (
        <ActivityPage
          events={activity}
          projects={projects}
          jobs={jobs}
          onOpen={openProject}
        />
      )
      break
    case 'project':
      page = (
        <ProjectPage
          key={shellRoute.id}
          project={projects.find((p) => p.id === shellRoute.id) ?? null}
          jobs={jobs}
          live={liveIds.has(shellRoute.id)}
          onBack={() => setRoute({ page: 'projects' })}
        />
      )
      break
    case 'connections':
      page = (
        <ConnectionsPage
          connections={connections}
          checking={checking}
          onRefresh={() => void refresh()}
          jobs={jobs}
          claude={claude}
          projects={snapshot?.projects ?? []}
        />
      )
      break
    case 'preferences':
      page = <PreferencesPage />
      break
    case 'how':
      page = (
        <HowItWorksPage
          onRestart={() => setRoute({ page: 'onboarding' })}
          onOpenConnections={() => setRoute({ page: 'connections' })}
        />
      )
      break
  }

  return (
    <div className="shell">
      <Sidebar route={shellRoute} onNavigate={setRoute} live={liveIds.size > 0} updateAvailable={updateReady} />
      <div className="shell-main">
        <TopBar
          query={query}
          onQuery={onQuery}
          jobs={jobs}
          health={health}
          onOpenConnections={() => setRoute({ page: 'connections' })}
          onCancelJob={onCancelJob}
        />
        <main className="content" ref={contentRef}>
          <div className="content-inner">
            {fromCache && snapshot !== null && (
              <p className="stale-banner" role="status">
                Dados de {formatClock(snapshot.generatedAt)}, atualizando…
              </p>
            )}
            {route === null ? (
              snapshotError !== null ? (
                <section className="page" aria-labelledby="snapshot-error-title">
                  <h1 className="page-title" id="snapshot-error-title">
                    Não foi possível carregar os projetos
                  </h1>
                  <p className="callout callout-error">{snapshotError}</p>
                  <button type="button" className="btn btn-primary" onClick={retry}>
                    Tentar de novo
                  </button>
                </section>
              ) : (
                <SkeletonRegion label="Carregando projetos" className="page">
                  <ul className="project-grid" aria-hidden="true">
                    {Array.from({ length: 6 }, (_, i) => (
                      <li key={i}>
                        <SkeletonCard />
                      </li>
                    ))}
                  </ul>
                </SkeletonRegion>
              )
            ) : (
              page
            )}
          </div>
        </main>
      </div>
      {overlay === 'palette' && <CommandPalette commands={commands} onRun={runCommand} onClose={() => setOverlay(null)} />}
      {overlay === 'help' && <ShortcutsHelp onClose={() => setOverlay(null)} />}
      <Toaster />
    </div>
  )
}

export default App

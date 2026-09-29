import { useEffect, useId, useRef, useState } from 'react'
import type { ConnectionCheck, JobView } from '../types/ragx-bridge'
import { RagxMark } from '../components/brand/RagxMark'
import { ConnectionGrid } from '../components/connections/ConnectionCard'
import { AddProjectFlow, type PickedProject } from '../components/project/AddProjectFlow'
import { HOW_IT_WORKS, HOW_IT_WORKS_TITLE } from '../components/onboarding/howItWorks'

const STEPS = [HOW_IT_WORKS_TITLE, 'Conexões', 'Projetos', 'Indexar'] as const
const LAST = STEPS.length - 1

const HOOKS_LABEL = 'Instalar hooks de git (mantém o índice na branch em que você está)'

/**
 * Configuração inicial em tela cheia: como funciona, conexões, escolher
 * projetos e indexar. Só o passo 4 ("Começar") enfileira alguma coisa;
 * "Começar" e "Pular configuração" marcam o onboarding como feito e chamam
 * `onFinish` (o `App` leva a Projetos).
 */
export function Onboarding({
  connections,
  checking,
  onRefresh,
  jobs,
  onFinish,
}: {
  connections: ConnectionCheck[] | null
  checking: boolean
  onRefresh: () => void
  jobs: readonly JobView[]
  onFinish: () => void
}) {
  const [step, setStep] = useState(0)
  const [picked, setPicked] = useState<PickedProject[]>([])
  const [installHooks, setInstallHooks] = useState(true)
  // Tokens que já entraram na fila: tentar de novo depois de uma falha só
  // reenvia o que faltou.
  const [queued, setQueued] = useState<ReadonlySet<string>>(new Set())
  const [failed, setFailed] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const titleId = useId()
  const titleRef = useRef<HTMLHeadingElement>(null)
  const moved = useRef(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  // Ao trocar de passo, o foco vai para o título novo (leitor de tela anuncia
  // o passo). Na primeira pintura, não rouba o foco de ninguém.
  useEffect(() => {
    if (moved.current) titleRef.current?.focus()
  }, [step])

  function go(to: number) {
    moved.current = true
    setFailed([])
    setStep(to)
  }

  const pending = picked.filter((p) => !queued.has(p.token))

  async function finish() {
    setBusy(true)
    try {
      await window.ragx.setOnboardingDone(true)
    } catch (err) {
      console.error('setOnboardingDone() falhou:', err)
    }
    onFinish()
  }

  async function start() {
    setBusy(true)
    setFailed([])
    const ok = new Set(queued)
    const notAdded: string[] = []
    // Um por vez, na ordem da lista: a fila é serial de qualquer jeito.
    for (const p of pending) {
      try {
        await window.ragx.enqueueJob({ kind: 'add-project', folderToken: p.token, installHooks })
        ok.add(p.token)
      } catch (err) {
        console.error('enqueueJob(add-project) falhou:', err)
        notAdded.push(p.name)
      }
    }
    if (!alive.current) return
    setQueued(ok)
    if (notAdded.length > 0) {
      setFailed(notAdded)
      setBusy(false)
      return
    }
    await finish()
  }

  const hasError = connections?.some((c) => c.state === 'error') ?? false

  let primary: { label: string; onClick: () => void }
  if (step === LAST) primary = { label: 'Começar', onClick: () => void start() }
  else if (step === 2 && picked.length === 0) primary = { label: 'Continuar sem adicionar', onClick: () => go(3) }
  else primary = { label: 'Continuar', onClick: () => go(step + 1) }

  return (
    <div className="onboarding">
      <header className="onboarding-top">
        <span className="onboarding-brand">
          <RagxMark size={22} className="onboarding-brand-mark" />
          <span className="onboarding-brand-name">RAGX</span> Configuração inicial
        </span>
        <button type="button" className="btn btn-quiet" onClick={() => void finish()} disabled={busy}>
          Pular configuração
        </button>
      </header>

      <main className="onboarding-main">
        <ol className="stepper" aria-label="Etapas da configuração">
          {STEPS.map((title, i) => (
            <li
              key={title}
              className={`stepper-item${i < step ? ' is-done' : ''}`}
              aria-current={i === step ? 'step' : undefined}
            >
              <span className="stepper-num" aria-hidden="true">
                {i + 1}
              </span>
              <span className="stepper-label">{title}</span>
            </li>
          ))}
        </ol>

        <section className="card onboarding-panel" aria-labelledby={titleId}>
          <p className="onboarding-count">
            Passo {step + 1} de {STEPS.length}
          </p>
          <h1 className="page-title onboarding-title" id={titleId} ref={titleRef} tabIndex={-1}>
            {STEPS[step]}
          </h1>

          {step === 0 && (
            <div className="prose">
              {HOW_IT_WORKS.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
          )}

          {step === 1 && (
            <div className="stack onboarding-body">
              <div className="onboarding-row">
                <p className="dim">Confira se o RAGX, o Claude Code e o Ollama estão prontos.</p>
                <button type="button" className="btn btn-sm" onClick={onRefresh} disabled={checking}>
                  {checking ? 'Verificando…' : 'Verificar agora'}
                </button>
              </div>
              <ConnectionGrid connections={connections} jobs={jobs} />
              {hasError && (
                <p className="callout callout-warning">Você pode continuar e resolver depois na tela Conexões.</p>
              )}
            </div>
          )}

          {/* Montado desde o início e só escondido: voltar do passo 4 mantém a pasta e as marcações. */}
          <div className="onboarding-body" hidden={step !== 2}>
            <p className="dim onboarding-intro">
              Escolha uma ou mais pastas; o RAGX encontra os projetos e os repositórios git dentro delas. Marque os
              que quer indexar.
            </p>
            <AddProjectFlow
              onSelectionChange={setPicked}
              installHooks={installHooks}
              onInstallHooksChange={setInstallHooks}
            />
          </div>

          {step === LAST && (
            <div className="stack onboarding-body">
              {pending.length > 0 ? (
                <>
                  <p>
                    {pending.length} projeto(s) vão ser indexados. Isso roda em segundo plano; acompanhe pela fila no
                    topo.
                  </p>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={installHooks}
                      onChange={(e) => setInstallHooks(e.target.checked)}
                    />
                    <span>{HOOKS_LABEL}</span>
                  </label>
                </>
              ) : (
                <p className="dim">Nenhum projeto marcado. Você pode adicionar depois na tela Projetos.</p>
              )}
              {failed.length > 0 && (
                <p className="callout callout-error" role="alert">
                  Não foi possível adicionar {failed.join(', ')}.
                </p>
              )}
            </div>
          )}
        </section>

        <footer className="onboarding-nav">
          {step > 0 && (
            <button type="button" className="btn" onClick={() => go(step - 1)} disabled={busy}>
              Voltar
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={primary.onClick} disabled={busy}>
            {primary.label}
          </button>
        </footer>
      </main>
    </div>
  )
}

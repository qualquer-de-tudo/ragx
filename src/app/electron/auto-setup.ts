/**
 * Ajuste automático (RAGX 1.0.1): o painel mantém sozinho o que faz o RAGX funcionar de ponta a ponta.
 *
 * 1. **Hooks do Claude Code.** Em cada perfil onde o RAGX já está ligado, completa o que falta (`ragx claude heal`): o
 *    aviso de edição, que faz o índice enxergar o que o agente edita, e o lembrete de busca. Quem ligou numa versão
 *    antiga ficava sem eles e nada avisava. Nunca liga um perfil desligado, e respeita o `--no-touch` escolhido à mão.
 * 2. **Hooks de git.** Em cada projeto com índice cujo status diz que os hooks não estão instalados, enfileira a
 *    instalação (a mesma tarefa do botão do projeto, então aparece na fila). Falha repetida não vira laço: um projeto
 *    que falhou só é tentado de novo depois de `RETRY_MS`.
 *
 * Desligável em Preferências (`autoSetup`, ligada por padrão). O módulo não importa `electron`: tudo entra por injeção.
 */

export interface AutoSetupState {
  /** A preferência está ligada? */
  enabled: boolean
  running: boolean
  /** ISO da última rodada que terminou; `null` antes da primeira. */
  lastRunAt: string | null
  claude: {
    /** Perfis conferidos na última rodada. */
    checked: number
    /** O que a última rodada instalou, em português ("empresa: aviso de edição, lembrete de busca"). */
    installed: string[]
    /** Mensagem quando o ragx falhou ou algum perfil não aceitou a instalação. */
    error: string | null
  }
  git: {
    /** Projetos para os quais a última rodada enfileirou a instalação. */
    queued: string[]
    /** Projetos que a fila recusou (já havia outra tarefa igual não conta). */
    failed: string[]
  }
}

export interface HealResult {
  healed: Array<{ name: string; installed: string[]; skipped: string[]; failed: string[] }>
  error?: string
}

export interface LocalProject {
  id: string
  name: string
  hooksInstalled: boolean | null
}

export interface AutoSetupDeps {
  enabled: () => boolean
  /** `ragx claude heal --json`: rejeita se o ragx não responde. */
  healClaude: () => Promise<HealResult>
  /** Projetos com pasta local e índice (do último snapshot). */
  projects: () => LocalProject[]
  /** Enfileira `hooks-install` do projeto; `false` quando a fila recusou. */
  installGitHooks: (projectId: string) => boolean
  onState: (state: AutoSetupState) => void
  now?: () => number
}

export interface AutoSetup {
  getState: () => AutoSetupState
  /** Roda agora (botão "Ajustar agora", ou a preferência que acabou de ser ligada). */
  run: () => Promise<AutoSetupState>
  /** O snapshot mudou: roda só se algum projeto está sem hooks de git e não foi tentado há pouco. */
  onSnapshot: () => void
}

/** Um projeto cuja instalação foi enfileirada é conferido de novo só depois disto, ainda que o status continue "sem hooks". */
export const RETRY_MS = 30 * 60_000

const PARTES: Record<string, string> = {
  hint: 'dica de início de sessão',
  touch: 'aviso de edição',
  nudge: 'lembrete de busca',
}

function parte(p: string): string {
  return PARTES[p] ?? p
}

export function createAutoSetup(deps: AutoSetupDeps): AutoSetup {
  const now = deps.now ?? Date.now
  const tentados = new Map<string, number>()
  let inFlight: Promise<AutoSetupState> | null = null
  let state: AutoSetupState = {
    enabled: deps.enabled(),
    running: false,
    lastRunAt: null,
    claude: { checked: 0, installed: [], error: null },
    git: { queued: [], failed: [] },
  }

  const set = (patch: Partial<AutoSetupState>) => {
    state = { ...state, ...patch }
    deps.onState(state)
  }

  async function runOnce(): Promise<AutoSetupState> {
    const enabled = deps.enabled()
    if (!enabled) {
      set({ enabled: false, running: false })
      return state
    }
    set({ enabled: true, running: true })

    let claude: AutoSetupState['claude']
    try {
      const out = await deps.healClaude()
      const installed = out.healed
        .filter((h) => h.installed.length > 0)
        .map((h) => `${h.name}: ${h.installed.map(parte).join(', ')}`)
      const falhas = out.healed.filter((h) => h.failed.length > 0).map((h) => `${h.name}: ${h.failed.map(parte).join(', ')}`)
      claude = {
        checked: out.healed.length,
        installed,
        error: falhas.length > 0 ? `Não consegui instalar: ${falhas.join('; ')}` : (out.error ?? null),
      }
    } catch (err) {
      claude = { checked: 0, installed: [], error: err instanceof Error ? err.message : String(err) }
    }

    const queued: string[] = []
    const failed: string[] = []
    const t = now()
    for (const p of deps.projects()) {
      if (p.hooksInstalled !== false) continue
      const last = tentados.get(p.id)
      if (last !== undefined && t - last < RETRY_MS) continue
      tentados.set(p.id, t)
      if (deps.installGitHooks(p.id)) queued.push(p.name)
      else failed.push(p.name)
    }

    set({
      running: false,
      lastRunAt: new Date(now()).toISOString(),
      claude,
      git: { queued, failed },
    })
    return state
  }

  function run(): Promise<AutoSetupState> {
    // Duas chamadas juntas (startup e snapshot) viram uma rodada só.
    inFlight ??= runOnce().finally(() => {
      inFlight = null
    })
    return inFlight
  }

  return {
    getState: () => ({ ...state, enabled: deps.enabled() }),
    run,
    onSnapshot() {
      if (!deps.enabled() || inFlight !== null) return
      const t = now()
      const pendente = deps.projects().some((p) => {
        if (p.hooksInstalled !== false) return false
        const last = tentados.get(p.id)
        return last === undefined || t - last >= RETRY_MS
      })
      if (pendente) void run()
    },
  }
}

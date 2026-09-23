import { neededModelsFor } from '../connections/checks'
import { httpGetJson } from '../system/http'
import type { StepCondition } from '../jobs/catalog'
import type { JobView, OllamaEnvironment, Snapshot } from '../../src/types/ragx-bridge'

/**
 * Peças do processo principal que ligam a detecção do Ollama (Task 1) ao
 * catálogo (Task 3) e à fila (Task 4). Ficam aqui, puras e testáveis, para o
 * `main.ts` só montar as dependências.
 */

const TAGS_URL = 'http://localhost:11434/api/tags'
const POLL_INTERVAL_MS = 1000
const POLL_REQUEST_TIMEOUT_MS = 3000

/** Condição `when` de um passo contra um ambiente detectado AGORA. Condição desconhecida lança (a fila vira falha legível). */
export function conditionFrom(env: OllamaEnvironment, c: StepCondition): boolean {
  switch (c) {
    case 'container-running':
      return env.container.running
    case 'container-exists':
      return env.container.exists
    case 'container-missing':
      return !env.container.exists
    case 'native-running':
      return env.native.running
    case 'native-missing':
      return !env.native.installed
    case 'native-not-running':
      return !env.native.running
    default:
      throw new Error(`condição desconhecida: ${String(c)}`)
  }
}

/**
 * Modelos de embedding que os projetos do snapshot pedem ao Ollama, sem
 * repetição e sem nome vazio. Mesma regra da checagem de conexões
 * (`neededModelsFor`): provider `ollama`, ou provider nulo com nome sem `/`.
 */
export function distinctRequiredModels(snapshot: Snapshot | null): string[] {
  return neededModelsFor(snapshot).models.filter((m) => m.trim().length > 0)
}

export interface WaitDeps {
  /** Uma sondagem da API com o tempo máximo dado; `true` se respondeu. */
  poll: (timeoutMs: number) => Promise<boolean>
  sleep: (ms: number) => Promise<void>
  now: () => number
}

/**
 * Sonda a API a cada 1 s até responder (`true`) ou o prazo acabar (`false`).
 * O prazo é daqui: a fila não tem timeout próprio. Cada sondagem espera no
 * máximo o que falta (nunca 0, que no Node desliga o timeout). Nunca rejeita.
 */
export async function waitForApi(timeoutMs: number, d: WaitDeps): Promise<boolean> {
  const deadline = d.now() + timeoutMs
  for (;;) {
    const requestTimeout = Math.max(1, Math.min(POLL_REQUEST_TIMEOUT_MS, deadline - d.now()))
    const up = await Promise.resolve()
      .then(() => d.poll(requestTimeout))
      .then(
      (answered) => answered === true,
      () => false,
    )
    if (up) return true
    const remaining = deadline - d.now()
    if (remaining <= 0) return false
    await d.sleep(Math.min(POLL_INTERVAL_MS, remaining))
    if (deadline - d.now() <= 0) return false
  }
}

export function defaultWaitDeps(): WaitDeps {
  return {
    poll: async (timeoutMs) => (await httpGetJson(TAGS_URL, timeoutMs)) !== null,
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    now: () => Date.now(),
  }
}

export interface OllamaEnvCache {
  /** Último ambiente detectado; `null` antes da primeira detecção. */
  get: () => OllamaEnvironment | null
  /** Sempre detecta de novo (condições da fila, checagem de conexões). */
  fresh: () => Promise<OllamaEnvironment>
  /** Junta-se à detecção em andamento, se houver (pedidos do renderer). */
  shared: () => Promise<OllamaEnvironment>
}

/**
 * Guarda o último `OllamaEnvironment`. Uma detecção que começou antes e
 * termina depois de outra mais nova não sobrescreve o resultado mais novo.
 */
export function createOllamaEnvCache(detect: () => Promise<OllamaEnvironment>): OllamaEnvCache {
  let latest: OllamaEnvironment | null = null
  let started = 0
  let applied = 0
  let inFlight: Promise<OllamaEnvironment> | null = null

  function fresh(): Promise<OllamaEnvironment> {
    const seq = ++started
    const run: Promise<OllamaEnvironment> = Promise.resolve()
      .then(() => detect())
      .then((env) => {
        if (seq > applied) {
          applied = seq
          latest = env
        }
        return env
      })
      .finally(() => {
        if (inFlight === run) inFlight = null
      })
    inFlight = run
    return run
  }

  return {
    get: () => latest,
    fresh,
    shared: () => inFlight ?? fresh(),
  }
}

/** O que o processo principal faz quando tarefas terminam (qualquer estado final). */
export function ollamaFollowUps(finished: readonly JobView[]): {
  /** Alguma tarefa `ollama-*` terminou: o caminho do executável pode ter mudado (ex.: `winget install`). */
  resetCache: boolean
  /** Troca de modo concluída: o modo a gravar como preferido (a que terminou por último). */
  persistMode: 'docker' | 'native' | null
} {
  const resetCache = finished.some((j) => j.kind.startsWith('ollama-'))
  let persistMode: 'docker' | 'native' | null = null
  let persistAt = -Infinity
  for (const j of finished) {
    if (j.state !== 'done') continue
    const mode = j.kind === 'ollama-use-native' ? 'native' : j.kind === 'ollama-use-docker' ? 'docker' : null
    if (mode === null) continue
    const at = j.finishedAt !== null ? Date.parse(j.finishedAt) : Number.NaN
    const when = Number.isFinite(at) ? at : -Infinity
    if (persistMode === null || when > persistAt) {
      persistMode = mode
      persistAt = when
    }
  }
  return { resetCache, persistMode }
}

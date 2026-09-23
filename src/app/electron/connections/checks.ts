import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileText } from '../system/exec'
import type { ExecFn } from '../system/exec'
import { httpGetJson } from '../system/http'
import { resolveRagx } from '../system/ragx-exe'
import type { ConnectionAction, ConnectionCheck, ConnectionState, Snapshot } from '../../src/types/ragx-bridge'

export interface CheckDeps {
  exec: ExecFn
  resolveRagx: () => string | null
  readFile: (p: string) => string | null
  exists: (p: string) => boolean
  httpGetJson: (url: string, timeoutMs: number) => Promise<unknown | null>
  homeDir: string
}

interface ClaudeMcpEntry {
  command?: string
}

interface ClaudeConfig {
  mcpServers?: Record<string, ClaudeMcpEntry>
  projects?: Record<string, { mcpServers?: Record<string, ClaudeMcpEntry> }>
}

interface OllamaTagsResponse {
  models?: Array<{ name?: string }>
}

function stateLabelFor(state: ConnectionState): string {
  if (state === 'ok') return 'Conectado'
  if (state === 'warn') return 'Atenção'
  return 'Não conectado'
}

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function lastFolderName(p: string): string {
  const parts = p.split(/[\\/]/).filter((part) => part.length > 0)
  return parts.length > 0 ? parts[parts.length - 1] : p
}

/**
 * `command` gravado em `mcpServers.ragx` de `~/.claude.json`:
 * - absoluto: existe fisicamente no disco (`d.exists`)?
 * - "nu" (sem diretório, ex.: o literal `ragx`, que é o que o instalador
 *   grava quando confia no PATH) e o nome-base é `ragx`/`ragx.exe`: ainda
 *   resolve pra algum lugar (`d.resolveRagx()`, mesma lógica usada pra
 *   achar o executável fora do PATH do app)?
 * - qualquer outro comando "nu" (não é o ragx): não dá pra verificar sem
 *   caminho - assume que existe.
 */
function commandNoLongerExists(command: string | undefined, d: CheckDeps): boolean {
  if (typeof command !== 'string' || command.length === 0) return false
  if (path.isAbsolute(command)) return !d.exists(command)
  const base = path.basename(command).toLowerCase()
  if (base === 'ragx' || base === 'ragx.exe') return d.resolveRagx() === null
  return false
}

/**
 * Nunca lança: `snapshot` vem do processo principal, mas pode ter passado
 * por serialização/deserialização de IPC ou vir de um mock malformado
 * em teste - `projects` pode não ser um array, e cada entrada pode não
 * ter `telemetry`. Qualquer forma inesperada vira "sem dado", não exceção.
 */
function maxLastCallAt(snapshot: Snapshot | null): string | null {
  if (!snapshot || !Array.isArray(snapshot.projects)) return null
  let best: string | null = null
  for (const proj of snapshot.projects) {
    const at = (proj as { telemetry?: { lastCallAt?: unknown } } | null | undefined)?.telemetry?.lastCallAt
    if (typeof at !== 'string') continue
    if (best === null || Date.parse(at) > Date.parse(best)) best = at
  }
  return best
}

// RAGX CLI ------------------------------------------------------------

export async function checkRagx(d: CheckDeps): Promise<ConnectionCheck> {
  const id = 'ragx' as const
  const title = 'RAGX CLI'
  try {
    const ragxPath = d.resolveRagx()
    if (ragxPath === null) {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'O comando ragx não foi encontrado nesta máquina.',
        facts: [],
        actions: [],
        help: 'Instale com o instalador do RAGX (install.ps1 no Windows, install.sh no Linux e macOS) e reabra o painel.',
        lastMcpCallAt: null,
      }
    }

    const result = await d.exec(ragxPath, ['--version'])
    if (result.code === 0) {
      return {
        id,
        title,
        state: 'ok',
        stateLabel: stateLabelFor('ok'),
        summary: 'Respondendo normalmente.',
        facts: [
          { label: 'Versão', value: result.stdout.trim() },
          { label: 'Local', value: ragxPath },
        ],
        actions: [],
        help: null,
        lastMcpCallAt: null,
      }
    }

    const stderrLines = result.stderr.split(/\r?\n/).slice(0, 3).join('\n').trim()
    return {
      id,
      title,
      state: 'error',
      stateLabel: stateLabelFor('error'),
      summary: 'O ragx foi encontrado mas não respondeu.',
      facts: [{ label: 'Local', value: ragxPath }],
      actions: [],
      help: stderrLines.length > 0 ? stderrLines : 'sem dados',
      lastMcpCallAt: null,
    }
  } catch (err) {
    return {
      id,
      title,
      state: 'error',
      stateLabel: stateLabelFor('error'),
      summary: `Falha inesperada ao checar o ragx: ${errMessage(err)}`,
      facts: [],
      actions: [],
      help: null,
      lastMcpCallAt: null,
    }
  }
}

// Claude Code -----------------------------------------------------------

export async function checkClaude(d: CheckDeps, snapshot: Snapshot | null): Promise<ConnectionCheck> {
  const id = 'claude' as const
  const title = 'Claude Code'
  // Valor seguro caso o próprio cálculo de `lastMcpCallAt` (que depende do
  // formato do snapshot) surpreenda - nunca deixa o campo undefined no
  // catch-all abaixo.
  let lastMcpCallAt: string | null = null

  try {
    // Computado dentro do try: um snapshot malformado (ex.: `projects` não
    // é array) não pode derrubar a checagem inteira antes mesmo de ler o
    // ~/.claude.json.
    lastMcpCallAt = maxLastCallAt(snapshot)

    const claudeJsonPath = path.join(d.homeDir, '.claude.json')
    const raw = d.readFile(claudeJsonPath)
    if (raw === null) {
      const registerAction: ConnectionAction = { kind: 'mcp-register', label: 'Registrar no Claude Code' }
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'O Claude Code ainda não foi usado nesta conta (sem ~/.claude.json).',
        facts: [],
        actions: [registerAction],
        help: null,
        lastMcpCallAt,
      }
    }

    let data: ClaudeConfig
    try {
      data = JSON.parse(raw) as ClaudeConfig
    } catch {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'Não foi possível ler ~/.claude.json.',
        facts: [],
        actions: [],
        help: null,
        lastMcpCallAt,
      }
    }

    const userEntry = data?.mcpServers?.ragx
    if (userEntry) {
      const command = userEntry.command
      const commandGone = commandNoLongerExists(command, d)
      if (commandGone) {
        return {
          id,
          title,
          state: 'warn',
          stateLabel: stateLabelFor('warn'),
          summary: 'O RAGX está registrado, mas o comando gravado não existe mais.',
          facts: [],
          actions: [{ kind: 'mcp-register', label: 'Registrar de novo' }],
          help: null,
          lastMcpCallAt,
        }
      }
      return {
        id,
        title,
        state: 'ok',
        stateLabel: stateLabelFor('ok'),
        summary: 'O RAGX está registrado para todos os projetos.',
        facts: [],
        actions: [],
        help: null,
        lastMcpCallAt,
      }
    }

    const projects = data?.projects ?? {}
    const localProjectPaths = Object.keys(projects).filter((p) => projects[p]?.mcpServers?.ragx)
    if (localProjectPaths.length > 0) {
      const names = localProjectPaths.slice(0, 5).map(lastFolderName)
      return {
        id,
        title,
        state: 'warn',
        stateLabel: stateLabelFor('warn'),
        summary: `O RAGX está registrado só em ${localProjectPaths.length} projeto(s). Nos outros o Claude Code não enxerga o índice.`,
        facts: [{ label: 'Projetos', value: names.join(', ') }],
        actions: [{ kind: 'mcp-register', label: 'Registrar para todos os projetos' }],
        help: null,
        lastMcpCallAt,
      }
    }

    return {
      id,
      title,
      state: 'error',
      stateLabel: stateLabelFor('error'),
      summary: 'O RAGX não está registrado no Claude Code.',
      facts: [],
      actions: [{ kind: 'mcp-register', label: 'Registrar no Claude Code' }],
      help: null,
      lastMcpCallAt,
    }
  } catch (err) {
    return {
      id,
      title,
      state: 'error',
      stateLabel: stateLabelFor('error'),
      summary: `Falha inesperada ao checar o Claude Code: ${errMessage(err)}`,
      facts: [],
      actions: [],
      help: null,
      lastMcpCallAt,
    }
  }
}

// Ollama (Docker) -------------------------------------------------------

function extractInstalledNames(json: unknown): string[] {
  if (typeof json !== 'object' || json === null) return []
  const models = (json as OllamaTagsResponse).models
  if (!Array.isArray(models)) return []
  const names: string[] = []
  for (const m of models) {
    if (m && typeof m.name === 'string') names.push(m.name)
  }
  return names
}

/**
 * Nunca lança: mesmo motivo de `maxLastCallAt` - `snapshot.projects` pode
 * não ser array, e cada entrada pode não ter os campos esperados
 * (`embeddingModel`/`embeddingProvider`/`name`). Entrada malformada é
 * ignorada (não conta como "necessita modelo"), não derruba a checagem.
 */
function neededModelsFor(snapshot: Snapshot | null): { models: string[]; projectNames: string[] } {
  if (!snapshot || !Array.isArray(snapshot.projects)) return { models: [], projectNames: [] }
  const relevant = snapshot.projects.filter((p): p is Snapshot['projects'][number] => {
    if (!p || typeof p !== 'object') return false
    const embeddingModel = p.embeddingModel
    const embeddingProvider = p.embeddingProvider
    return (
      typeof embeddingModel === 'string' &&
      (embeddingProvider === 'ollama' || (embeddingProvider === null && !embeddingModel.includes('/')))
    )
  })
  const models = Array.from(new Set(relevant.map((p) => p.embeddingModel as string)))
  const projectNames = relevant.map((p) => (typeof p.name === 'string' ? p.name : 'projeto sem nome'))
  return { models, projectNames }
}

function formatDependents(names: string[]): string {
  if (names.length === 0) return 'nenhum projeto'
  const shown = names.slice(0, 3).join(', ')
  return `${names.length} projeto(s): ${shown}`
}

export async function checkOllama(d: CheckDeps, snapshot: Snapshot | null): Promise<ConnectionCheck> {
  const id = 'ollama' as const
  const title = 'Ollama (Docker)'
  // Default seguro pro catch-all: se o próprio cálculo de dependências
  // falhar de forma totalmente inesperada, o card de erro ainda tem um
  // `dependFact` válido em vez de referenciar algo não inicializado.
  let dependFact = { label: 'Projetos que dependem', value: formatDependents([]) }
  const semDadosFact = { label: 'Modelos instalados', value: 'sem dados' }

  try {
    // Computado dentro do try: um snapshot malformado (ex.: `projects` com
    // entradas sem os campos esperados) não pode derrubar a checagem
    // inteira antes mesmo de perguntar pro Docker se o container existe.
    const { models: needed, projectNames } = neededModelsFor(snapshot)
    dependFact = { label: 'Projetos que dependem', value: formatDependents(projectNames) }

    const ps = await d.exec('docker', ['ps', '-a', '--filter', 'name=^ollama$', '--format', '{{.State}}'])
    if (ps.code !== 0 && (ps.notFound === true || /ENOENT/.test(ps.stderr))) {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'O Docker não está instalado nesta máquina.',
        facts: [semDadosFact, dependFact],
        actions: [],
        help: 'Instale o Docker Desktop e reabra o painel.',
        lastMcpCallAt: null,
      }
    }
    if (ps.code !== 0) {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'O Docker não está rodando.',
        facts: [semDadosFact, dependFact],
        actions: [],
        help: 'Abra o Docker Desktop e aguarde ele iniciar.',
        lastMcpCallAt: null,
      }
    }

    const trimmed = ps.stdout.trim()
    if (trimmed === '') {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'Não existe um container chamado ollama.',
        facts: [semDadosFact, dependFact],
        actions: [],
        help: 'Crie com: docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama',
        lastMcpCallAt: null,
      }
    }

    const state = trimmed.split(/\r?\n/)[0].trim()
    if (state !== 'running') {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'O container ollama está parado.',
        facts: [semDadosFact, dependFact],
        actions: [{ kind: 'ollama-start', label: 'Iniciar container' }],
        help: null,
        lastMcpCallAt: null,
      }
    }

    const json = await d.httpGetJson('http://localhost:11434/api/tags', 3000)
    if (json === null) {
      return {
        id,
        title,
        state: 'error',
        stateLabel: stateLabelFor('error'),
        summary: 'O container está rodando mas a API não responde na porta 11434.',
        facts: [semDadosFact, dependFact],
        actions: [],
        help: null,
        lastMcpCallAt: null,
      }
    }

    const installed = extractInstalledNames(json)
    const modelsFact = { label: 'Modelos instalados', value: installed.length > 0 ? installed.join(', ') : 'nenhum' }
    const missing = needed.filter((m) => !installed.some((inst) => inst === m || inst === `${m}:latest`))

    if (missing.length > 0) {
      return {
        id,
        title,
        state: 'warn',
        stateLabel: stateLabelFor('warn'),
        summary: `Falta baixar ${missing.length} modelo(s).`,
        facts: [modelsFact, dependFact],
        actions: missing.map((m) => ({ kind: 'ollama-pull' as const, label: `Baixar ${m}`, model: m })),
        help: null,
        lastMcpCallAt: null,
      }
    }

    return {
      id,
      title,
      state: 'ok',
      stateLabel: stateLabelFor('ok'),
      summary: 'Rodando, com os modelos que os projetos usam.',
      facts: [modelsFact, dependFact],
      actions: [],
      help: null,
      lastMcpCallAt: null,
    }
  } catch (err) {
    return {
      id,
      title,
      state: 'error',
      stateLabel: stateLabelFor('error'),
      summary: `Falha inesperada ao checar o Ollama: ${errMessage(err)}`,
      facts: [dependFact],
      actions: [],
      help: null,
      lastMcpCallAt: null,
    }
  }
}

// ------------------------------------------------------------------------

/**
 * Cada `check*` já tem seu próprio try/catch cobrindo o corpo inteiro, mas
 * `checkAll` não confia só nisso: se uma dependência injetada tiver um bug
 * e lançar num lugar que escape desse try (ex.: um erro de programação
 * fora do escopo hoje coberto), a promessa individual rejeita - sem este
 * guard, `Promise.all` rejeitaria a chamada inteira e nenhum dos três
 * cards apareceria no painel. Com o guard, uma checagem quebrada vira só
 * o card dela em `error`, as outras duas continuam normais.
 */
function guardCheck(id: ConnectionCheck['id'], title: string, run: () => Promise<ConnectionCheck>): Promise<ConnectionCheck> {
  return run().catch(
    (err: unknown): ConnectionCheck => ({
      id,
      title,
      state: 'error',
      stateLabel: stateLabelFor('error'),
      summary: `Falha inesperada ao checar ${title}: ${errMessage(err)}`,
      facts: [],
      actions: [],
      help: null,
      lastMcpCallAt: null,
    }),
  )
}

export async function checkAll(d: CheckDeps, snapshot: Snapshot | null): Promise<ConnectionCheck[]> {
  return Promise.all([
    guardCheck('ragx', 'RAGX CLI', () => checkRagx(d)),
    guardCheck('claude', 'Claude Code', () => checkClaude(d, snapshot)),
    guardCheck('ollama', 'Ollama (Docker)', () => checkOllama(d, snapshot)),
  ])
}

export function defaultCheckDeps(): CheckDeps {
  return {
    exec: execFileText,
    resolveRagx: () => resolveRagx(),
    readFile: (p) => {
      try {
        return fs.readFileSync(p, 'utf-8')
      } catch {
        return null
      }
    },
    exists: (p) => fs.existsSync(p),
    httpGetJson,
    homeDir: os.homedir(),
  }
}

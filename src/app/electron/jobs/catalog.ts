import path from 'node:path'
import { chooseStartMode } from '../ollama/choose-start'
import type { JobKind, JobRequest, OllamaEnvironment } from '../../src/types/ragx-bridge'

export type StepCondition =
  | 'container-running'
  | 'container-exists'
  | 'container-missing'
  | 'native-running'
  | 'native-missing'
  | 'native-not-running'

export interface Step {
  cmd: 'ragx' | 'docker' | 'ollama' | 'winget' | 'powershell' | 'pkill'
  args: string[]
  cwd: string | null
  progress: boolean
  /**
   * Só roda se esta pasta estiver dentro de um repositório git (checado pela
   * fila logo antes do passo); fora de git, o passo é pulado com uma nota.
   */
  onlyIfGitRepo?: string
  /** Só roda se a condição for verdadeira NA HORA (avaliada pela fila). Falsa: passo pulado. */
  when?: StepCondition
  /** Processo de longa vida (ex.: `ollama serve`): a fila só confirma que nasceu e segue. */
  detached?: boolean
  /** Passo sem processo: espera `GET /api/tags` responder (até `timeoutMs`). */
  waitForOllamaApi?: { timeoutMs: number }
  /** Códigos de saída que contam como sucesso além de 0 (ex.: `pkill` 1 = nada a encerrar). */
  okExitCodes?: number[]
  /** Nota registrada no job quando o passo é pulado por `when`. */
  skipNote?: string
  /**
   * Variáveis somadas ao ambiente do processo. É por aqui que um dado da
   * máquina (ex.: a pasta do Ollama local) chega a um script, nunca
   * interpolado no texto do comando.
   */
  env?: Record<string, string>
}

export interface ResolvedJob {
  kind: JobKind
  label: string
  projectId: string | null
  steps: Step[]
  /**
   * Chave de dedupe usada por `JobQueue.enqueue` entre tarefas `queued`/
   * `running`. Não é só `kind`+`projectId`: para kinds sem projeto
   * (`ollama-pull`, `add-project`) isso colidiria pedidos diferentes (dois
   * modelos distintos, ou duas pastas distintas) num só. Formato geral:
   * `${kind}|${projectId ?? ''}|${model ?? ''}`; `add-project` usa o
   * caminho da pasta resolvida no lugar do modelo, já que é isso que
   * distingue um pedido do outro nesse kind.
   */
  dedupeKey: string
  /** Modelo pedido: só em `ollama-pull`; `null` nos outros tipos. Vai para o `JobView`. */
  model: string | null
  /** Pasta do `add-project` (para a conferência no hub depois do último passo). */
  folder?: string
  /** Avisos do catálogo (ex.: modelo inválido ignorado); a fila os registra no job (Task 4). */
  notes?: string[]
}

export interface CatalogContext {
  projectById: (id: string) => { id: string; name: string; path: string | null } | undefined
  folderByToken: (token: string) => string | undefined
  /** Último ambiente detectado (o painel atualiza a cada checagem); `null` antes da primeira. */
  ollamaEnv?: () => OllamaEnvironment | null
  /** Modelos de embedding em uso pelos projetos com provider ollama, sem repetição. */
  requiredModels?: () => string[]
  /** Modo que o usuário escolheu por último (persistido pelo processo principal); `null` se nunca escolheu. */
  preferredOllamaMode?: () => 'docker' | 'native' | null
}

/** Recusa de `resolveJob`: pedido fora do catálogo fechado, nunca vira processo. */
export class JobRejected extends Error {}

/**
 * Só aceita nomes de modelo Ollama plausíveis (com namespace/tag opcionais).
 * Qualquer coisa fora disso (`x; rm -rf /`, `--help`) é recusada antes de
 * virar argumento de `docker exec ... ollama pull`.
 */
export const MODEL_PATTERN = /^[a-z0-9][a-z0-9._-]*(\/[a-z0-9][a-z0-9._-]*)?(:[a-z0-9._-]+)?$/i

const KNOWN_KINDS: ReadonlySet<string> = new Set<JobKind>([
  'add-project',
  'update',
  'embed',
  'reindex-full',
  'sync',
  'graph',
  'dictionary',
  'hooks-install',
  'hooks-uninstall',
  'remove-from-hub',
  'mcp-register',
  'ollama-start',
  'ollama-pull',
  'ollama-use-native',
  'ollama-use-docker',
  'ollama-stop',
])

/** Kinds que precisam de um projeto conhecido no hub (`projectById`). */
const PROJECT_KINDS: ReadonlySet<string> = new Set<JobKind>([
  'update',
  'embed',
  'reindex-full',
  'sync',
  'graph',
  'dictionary',
  'hooks-install',
  'hooks-uninstall',
  'remove-from-hub',
])

/** Dentre os kinds de projeto, os que precisam de `path` (rodam fora do cwd do projeto ou passam o caminho). */
const NEEDS_PATH_KINDS: ReadonlySet<string> = new Set<JobKind>([
  'update',
  'embed',
  'reindex-full',
  'sync',
  'graph',
  'dictionary',
  'hooks-install',
  'hooks-uninstall',
])

function dedupeKey(kind: JobKind, projectId: string | null, model?: string): string {
  return `${kind}|${projectId ?? ''}|${model ?? ''}`
}

function lastFolderName(p: string): string {
  const parts = p.split(/[\\/]/).filter((part) => part.length > 0)
  return parts.length > 0 ? parts[parts.length - 1] : p
}

function progressStep(path: string, extraArgs: string[] = []): Step {
  return { cmd: 'ragx', args: ['index', path, ...extraArgs, '--progress', '--source', 'panel'], cwd: null, progress: true }
}

function plainStep(cmd: Step['cmd'], args: string[]): Step {
  return { cmd, args, cwd: null, progress: false }
}

function serveStep(): Step {
  return {
    ...plainStep('ollama', ['serve']),
    detached: true,
    when: 'native-not-running',
    skipNote: 'O Ollama local já estava rodando.',
  }
}

function waitApiStep(): Step {
  return { ...plainStep('ollama', []), waitForOllamaApi: { timeoutMs: 60000 } }
}

/**
 * Encerra, no Windows, só o Ollama instalado na pasta `OLLAMA_DIR` (a do
 * executável detectado): `ollama.exe` e `ollama app.exe` (a bandeja) cujo
 * `ExecutablePath` começa nessa pasta. Outro app que traz o seu próprio
 * `ollama.exe` (ex.: AnythingLLM) fica de fora, o que um `taskkill /IM`
 * não garantia.
 *
 * A pasta chega pelo ambiente do processo (`Step.env`), nunca dentro deste
 * texto. `StartsWith` com `OrdinalIgnoreCase` compara sem curingas (um `[`
 * no caminho não vira padrão, como viraria no `-like`), e a barra no fim
 * impede `...\Ollama` de casar com `...\Ollama2`. Pasta vazia: não encerra
 * nada. Sai com 1 só se algum desses processos continuar vivo depois.
 */
export const STOP_NATIVE_WINDOWS_SCRIPT = [
  '$d = $env:OLLAMA_DIR',
  'if (-not $d) { exit 0 }',
  "$d = $d.TrimEnd('\\') + '\\'",
  "$names = @('ollama.exe', 'ollama app.exe')",
  'function Get-Alvos { @(Get-CimInstance Win32_Process | Where-Object { $names -contains $_.Name -and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($d, [System.StringComparison]::OrdinalIgnoreCase) }) }',
  'Get-Alvos | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }',
  'Start-Sleep -Milliseconds 500',
  "if ((Get-Alvos).Count -gt 0) { [Console]::Error.WriteLine('O Ollama local continua rodando.'); exit 1 }",
  'exit 0',
].join('; ')

/**
 * Encerra o Ollama nativo: no Windows, um passo de PowerShell que só mata o
 * Ollama da pasta detectada (sem caminho conhecido, não há passo); nos
 * demais, `pkill -x ollama` (1 = nada a encerrar).
 */
function stopNativeSteps(env: OllamaEnvironment | null): Step[] {
  const win = (env?.platform ?? process.platform) === 'win32'
  if (!win) {
    return [{ ...plainStep('pkill', ['-x', 'ollama']), when: 'native-running', okExitCodes: [1] }]
  }
  const exe = env?.native.path ?? null
  if (exe === null) return []
  return [
    {
      ...plainStep('powershell', ['-NoProfile', '-NonInteractive', '-Command', STOP_NATIVE_WINDOWS_SCRIPT]),
      when: 'native-running',
      env: { OLLAMA_DIR: path.win32.dirname(exe) },
    },
  ]
}

/** Modelos requeridos, cada um passando por `MODEL_PATTERN`; inválido é ignorado com nota, nunca vira argumento. */
function requiredModelsOf(ctx: CatalogContext): { models: string[]; notes: string[] } {
  const models: string[] = []
  const notes: string[] = []
  for (const m of ctx.requiredModels?.() ?? []) {
    if (typeof m === 'string' && MODEL_PATTERN.test(m)) {
      if (!models.includes(m)) models.push(m)
    } else {
      notes.push(`Modelo ignorado por nome inválido: ${String(m)}`)
    }
  }
  return { models, notes }
}

interface ProjectInfo {
  id: string
  name: string
  path: string | null
}

function requireProject(req: JobRequest, ctx: CatalogContext, needsPath: boolean): { project: ProjectInfo; path: string } {
  if (typeof req.projectId !== 'string' || req.projectId.length === 0) {
    throw new JobRejected(`tarefa "${req.kind}" precisa de projectId`)
  }
  const project = ctx.projectById(req.projectId)
  if (project === undefined) {
    throw new JobRejected(`projeto desconhecido: ${req.projectId}`)
  }
  if (needsPath && project.path === null) {
    throw new JobRejected(`projeto "${project.name}" não tem pasta local (só federação)`)
  }
  return { project, path: project.path ?? '' }
}

/**
 * Valida o tipo dos campos opcionais que vieram no pedido, mesmo os que este
 * `kind` não usa - um `installHooks` não booleano é recusado mesmo se o
 * `kind` do pedido nem usasse esse campo, porque um renderer comprometido
 * pode mandar qualquer coisa.
 */
function validateFieldTypes(req: JobRequest): void {
  if (req.projectId !== undefined && typeof req.projectId !== 'string') {
    throw new JobRejected('projectId precisa ser texto')
  }
  if (req.folderToken !== undefined && typeof req.folderToken !== 'string') {
    throw new JobRejected('folderToken precisa ser texto')
  }
  if (req.model !== undefined && typeof req.model !== 'string') {
    throw new JobRejected('model precisa ser texto')
  }
  if (req.installHooks !== undefined && typeof req.installHooks !== 'boolean') {
    throw new JobRejected('installHooks precisa ser booleano')
  }
}

/** Falha ao ler o ambiente do Ollama vira recusa legível, nunca exceção crua para o renderer. */
function guarded<T>(fn: (() => T) | undefined): (() => T) | undefined {
  if (fn === undefined) return undefined
  return () => {
    try {
      return fn()
    } catch {
      throw new JobRejected('Não foi possível ler o ambiente do Ollama.')
    }
  }
}

export function resolveJob(req: JobRequest, rawCtx: CatalogContext): ResolvedJob {
  const ctx: CatalogContext = {
    ...rawCtx,
    ollamaEnv: guarded(rawCtx.ollamaEnv),
    requiredModels: guarded(rawCtx.requiredModels),
    preferredOllamaMode: guarded(rawCtx.preferredOllamaMode),
  }
  const job = resolveSteps(req, ctx)
  // Só chega aqui um `ollama-pull` com modelo já validado por `MODEL_PATTERN`.
  return { ...job, model: job.kind === 'ollama-pull' ? (req.model as string) : null }
}

function resolveSteps(req: JobRequest, ctx: CatalogContext): Omit<ResolvedJob, 'model'> {
  if (req === null || typeof req !== 'object' || typeof req.kind !== 'string' || !KNOWN_KINDS.has(req.kind)) {
    throw new JobRejected(`tarefa fora do catálogo: ${String((req as { kind?: unknown } | null)?.kind)}`)
  }
  validateFieldTypes(req)

  const kind = req.kind

  if (kind === 'add-project') {
    if (typeof req.folderToken !== 'string' || req.folderToken.length === 0) {
      throw new JobRejected('add-project precisa de folderToken')
    }
    const folder = ctx.folderByToken(req.folderToken)
    if (folder === undefined) {
      throw new JobRejected(`token de pasta desconhecido: ${req.folderToken}`)
    }
    const steps: Step[] = [
      { cmd: 'ragx', args: ['init', folder], cwd: null, progress: false },
      progressStep(folder),
    ]
    if (req.installHooks === true) {
      // Pasta fora de git: a fila pula este passo com uma nota em vez de
      // derrubar a tarefa inteira no último passo.
      steps.push({ cmd: 'ragx', args: ['hooks', 'install', folder], cwd: null, progress: false, onlyIfGitRepo: folder })
    }
    return {
      kind,
      label: `Adicionar ${lastFolderName(folder)}`,
      projectId: null,
      steps,
      dedupeKey: `add-project|${folder}`,
      folder,
    }
  }

  if (kind === 'mcp-register') {
    return {
      kind,
      label: 'Registrar o RAGX no Claude Code',
      projectId: null,
      steps: [{ cmd: 'ragx', args: ['mcp', 'install', '--client', 'claude-code'], cwd: null, progress: false }],
      dedupeKey: dedupeKey(kind, null),
    }
  }

  if (kind === 'ollama-start') {
    const env = ctx.ollamaEnv?.() ?? null
    let steps: Step[] = [plainStep('docker', ['start', 'ollama'])]
    let label = 'Iniciar o container ollama'
    if (env !== null) {
      // A mesma escolha dá o texto do botão na checagem de conexões.
      const chosen = chooseStartMode(env, ctx.preferredOllamaMode?.() ?? null)
      if (chosen === 'docker') {
        steps = [{ ...plainStep('docker', ['start', 'ollama']), when: 'container-exists' }]
      } else if (chosen === 'native') {
        steps = [serveStep(), waitApiStep()]
        label = 'Iniciar o Ollama local'
      }
    }
    return { kind, label, projectId: null, steps, dedupeKey: dedupeKey(kind, null) }
  }

  if (kind === 'ollama-use-native') {
    const env = ctx.ollamaEnv?.() ?? null
    if (env !== null && !env.canInstallNative && !env.native.installed) {
      throw new JobRejected(
        'A instalação automática do Ollama só existe no Windows. Baixe em https://ollama.com/download e abra o painel de novo.',
      )
    }
    const { models, notes } = requiredModelsOf(ctx)
    // Instala ANTES de parar o container: se o `winget` falhar (o passo lento
    // e arriscado), o Docker continua servindo e a máquina nunca fica sem Ollama.
    const steps: Step[] = [
      {
        ...plainStep('winget', [
          'install',
          '-e',
          '--id',
          'Ollama.Ollama',
          '--silent',
          '--accept-package-agreements',
          '--accept-source-agreements',
        ]),
        when: 'native-missing',
      },
      { ...plainStep('docker', ['stop', 'ollama']), when: 'container-running', okExitCodes: [] },
      serveStep(),
      waitApiStep(),
      ...models.map((m) => plainStep('ollama', ['pull', m])),
    ]
    return { kind, label: 'Usar o Ollama local', projectId: null, steps, dedupeKey: dedupeKey(kind, null), notes }
  }

  if (kind === 'ollama-use-docker') {
    const env = ctx.ollamaEnv?.() ?? null
    if (env !== null && !env.docker.installed) {
      throw new JobRejected('O Docker não está instalado nesta máquina.')
    }
    // Docker parado: o `docker run` falharia DEPOIS de o Ollama local já ter
    // sido encerrado. Recusa antes de mexer em qualquer coisa.
    if (env !== null && !env.docker.running) {
      throw new JobRejected('Abra o Docker Desktop e aguarde ele iniciar.')
    }
    const { models, notes } = requiredModelsOf(ctx)
    // `--gpus all` precisa vir ANTES da imagem: depois dela viraria argumento do container.
    const gpu = env?.gpu.vendor === 'nvidia' ? ['--gpus', 'all'] : []
    const steps: Step[] = [
      // A imagem (o download lento) vem enquanto o Ollama local ainda serve:
      // uma falha de rede aqui não deixa a máquina sem nenhum Ollama.
      { ...plainStep('docker', ['pull', 'ollama/ollama']), when: 'container-missing' },
      ...stopNativeSteps(env),
      { ...plainStep('docker', ['start', 'ollama']), when: 'container-exists' },
      {
        ...plainStep('docker', [
          'run',
          '-d',
          '--name',
          'ollama',
          '-p',
          '11434:11434',
          '-v',
          'ollama:/root/.ollama',
          '--restart',
          'unless-stopped',
          ...gpu,
          'ollama/ollama',
        ]),
        when: 'container-missing',
      },
      waitApiStep(),
      ...models.map((m) => plainStep('docker', ['exec', 'ollama', 'ollama', 'pull', m])),
    ]
    return { kind, label: 'Usar o Ollama no Docker', projectId: null, steps, dedupeKey: dedupeKey(kind, null), notes }
  }

  if (kind === 'ollama-stop') {
    const env = ctx.ollamaEnv?.() ?? null
    const steps: Step[] = [
      { ...plainStep('docker', ['stop', 'ollama']), when: 'container-running', okExitCodes: [] },
      ...stopNativeSteps(env),
    ]
    return { kind, label: 'Parar o Ollama', projectId: null, steps, dedupeKey: dedupeKey(kind, null) }
  }

  if (kind === 'ollama-pull') {
    if (typeof req.model !== 'string' || !MODEL_PATTERN.test(req.model)) {
      throw new JobRejected(`nome de modelo inválido: ${String(req.model)}`)
    }
    const native = ctx.ollamaEnv?.()?.mode === 'native'
    return {
      kind,
      label: `Baixar o modelo ${req.model}`,
      projectId: null,
      steps: [
        native
          ? plainStep('ollama', ['pull', req.model])
          : plainStep('docker', ['exec', 'ollama', 'ollama', 'pull', req.model]),
      ],
      dedupeKey: dedupeKey(kind, null, req.model),
    }
  }

  if (kind === 'remove-from-hub') {
    const { project } = requireProject(req, ctx, false)
    return {
      kind,
      label: `Remover ${project.name} do hub`,
      projectId: project.id,
      // `--`: um nome de projeto começando com `-` nunca vira opção do CLI.
      steps: [{ cmd: 'ragx', args: ['project', 'unregister', '--', project.name], cwd: null, progress: false }],
      dedupeKey: dedupeKey(kind, project.id),
    }
  }

  // Demais kinds: tarefas de projeto existente, todas precisando de `path`.
  if (!PROJECT_KINDS.has(kind)) {
    // Defensivo: todo kind conhecido cai em algum ramo acima; se um novo
    // kind for adicionado a `KNOWN_KINDS` sem um ramo correspondente, isso
    // recusa em vez de deixar passar sem `steps`.
    throw new JobRejected(`tarefa "${kind}" sem implementação no catálogo`)
  }
  const { project, path } = requireProject(req, ctx, NEEDS_PATH_KINDS.has(kind))

  switch (kind) {
    case 'update':
      return {
        kind,
        label: `Atualizar ${project.name}`,
        projectId: project.id,
        steps: [progressStep(path)],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'embed':
      return {
        kind,
        label: `Gerar embeddings em ${project.name}`,
        projectId: project.id,
        steps: [progressStep(path, ['--embed-only'])],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'reindex-full':
      return {
        kind,
        label: `Reindexar ${project.name} do zero`,
        projectId: project.id,
        steps: [progressStep(path, ['--full'])],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'sync':
      return {
        kind,
        label: `Sincronizar knowledge de ${project.name}`,
        projectId: project.id,
        steps: [{ cmd: 'ragx', args: ['sync'], cwd: path, progress: false }],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'graph':
      return {
        kind,
        label: `Reconstruir grafo de ${project.name}`,
        projectId: project.id,
        steps: [{ cmd: 'ragx', args: ['graph', 'rebuild'], cwd: path, progress: false }],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'dictionary':
      return {
        kind,
        label: `Gerar dicionário de ${project.name}`,
        projectId: project.id,
        steps: [{ cmd: 'ragx', args: ['dictionary', 'generate'], cwd: path, progress: false }],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'hooks-install':
      return {
        kind,
        label: `Instalar hooks em ${project.name}`,
        projectId: project.id,
        steps: [{ cmd: 'ragx', args: ['hooks', 'install', path], cwd: null, progress: false }],
        dedupeKey: dedupeKey(kind, project.id),
      }
    case 'hooks-uninstall':
      return {
        kind,
        label: `Remover hooks de ${project.name}`,
        projectId: project.id,
        steps: [{ cmd: 'ragx', args: ['hooks', 'uninstall', path], cwd: null, progress: false }],
        dedupeKey: dedupeKey(kind, project.id),
      }
    default:
      throw new JobRejected(`tarefa "${String(kind)}" sem implementação no catálogo`)
  }
}

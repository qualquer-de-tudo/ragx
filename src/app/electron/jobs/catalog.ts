import type { JobKind, JobRequest } from '../../src/types/ragx-bridge'

export interface Step {
  cmd: 'ragx' | 'docker'
  args: string[]
  cwd: string | null
  progress: boolean
  /**
   * Só roda se esta pasta estiver dentro de um repositório git (checado pela
   * fila logo antes do passo); fora de git, o passo é pulado com uma nota.
   */
  onlyIfGitRepo?: string
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
}

export interface CatalogContext {
  projectById: (id: string) => { id: string; name: string; path: string | null } | undefined
  folderByToken: (token: string) => string | undefined
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

export function resolveJob(req: JobRequest, ctx: CatalogContext): ResolvedJob {
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
    return {
      kind,
      label: 'Iniciar o container ollama',
      projectId: null,
      steps: [{ cmd: 'docker', args: ['start', 'ollama'], cwd: null, progress: false }],
      dedupeKey: dedupeKey(kind, null),
    }
  }

  if (kind === 'ollama-pull') {
    if (typeof req.model !== 'string' || !MODEL_PATTERN.test(req.model)) {
      throw new JobRejected(`nome de modelo inválido: ${String(req.model)}`)
    }
    return {
      kind,
      label: `Baixar o modelo ${req.model}`,
      projectId: null,
      steps: [{ cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', req.model], cwd: null, progress: false }],
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

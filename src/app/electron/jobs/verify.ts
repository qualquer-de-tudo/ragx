import fs from 'node:fs'
import path from 'node:path'
import { readHubRegistry } from '../data/hub'
import type { HubProject } from '../data/types'
import type { ResolvedJob } from './catalog'

export interface VerifyDeps {
  readRegistry: () => HubProject[]
  /** Conteúdo do arquivo, ou `null` se não der para ler. */
  readFile: (p: string) => string | null
  platform: NodeJS.Platform
}

export function defaultVerifyDeps(): VerifyDeps {
  return {
    readRegistry: readHubRegistry,
    readFile: (p) => {
      try {
        return fs.readFileSync(p, 'utf-8')
      } catch {
        return null
      }
    },
    platform: process.platform,
  }
}

const NOT_IN_PANEL = 'O projeto foi indexado, mas não entrou no painel'

function normalizeForCompare(p: string, platform: NodeJS.Platform): string {
  let s = p.replace(/\\/g, '/')
  while (s.length > 1 && s.endsWith('/') && !/^[A-Za-z]:\/$/.test(s)) s = s.slice(0, -1)
  // No Windows, `C:\X` e `c:\x` são a mesma pasta; noutro SO, não.
  return platform === 'win32' ? s.toLowerCase() : s
}

function lastFolderName(p: string): string {
  const parts = p.split(/[\\/]/).filter((part) => part.length > 0)
  return parts.length > 0 ? parts[parts.length - 1] : p
}

function unquote(raw: string): string | null {
  const double = /^"((?:[^"\\]|\\.)*)"/.exec(raw)
  if (double) return double[1].replace(/\\(["\\])/g, '$1')
  const single = /^'([^']*)'/.exec(raw)
  if (single) return single[1]
  return null
}

/**
 * Leitura mínima, por linha, de `name` e `visibility` da seção `[project]`
 * do `ragx.toml` (o arquivo de configuração do próprio RAGX). Só serve para
 * explicar por que um projeto não entrou no hub - não é um parser de TOML.
 */
export function parseProjectToml(text: string): { name: string | null; visibility: string | null } {
  let section: string | null = null
  let name: string | null = null
  let visibility: string | null = null
  for (const rawLine of text.split(/\r\n|\n|\r/)) {
    const line = rawLine.trim()
    if (line.length === 0 || line.startsWith('#')) continue
    const header = /^\[([^\]]+)\]/.exec(line)
    if (header) {
      section = header[1].trim()
      continue
    }
    if (section !== 'project') continue
    const kv = /^(name|visibility)\s*=\s*(.*)$/.exec(line)
    if (!kv) continue
    const value = unquote(kv[2])
    if (value === null) continue
    if (kv[1] === 'name') name = value
    else visibility = value
  }
  return { name, visibility }
}

/**
 * `ragx init` registra no hub em modo "melhor esforço" e engole a falha
 * (colisão de nome - `name` é UNIQUE no hub - ou projeto `private`). Sem esta
 * conferência, o `add-project` terminava "Concluída" sem card nenhum no
 * painel. Devolve o texto do erro, ou `null` quando a pasta está no hub.
 */
export function verifyAddProject(folder: string, d: VerifyDeps): string | null {
  let registry: HubProject[]
  try {
    registry = d.readRegistry()
  } catch (err) {
    // registry.json em escrita concorrente: sem dado para acusar a tarefa.
    console.error('verifyAddProject: não foi possível ler o registry do hub:', err)
    return null
  }

  const target = normalizeForCompare(folder, d.platform)
  if (registry.some((p) => p.path !== null && normalizeForCompare(p.path, d.platform) === target)) return null

  const toml = d.readFile(path.join(folder, 'ragx.toml'))
  const cfg = toml !== null ? parseProjectToml(toml) : { name: null, visibility: null }

  if (cfg.visibility === 'private') {
    return `${NOT_IN_PANEL} porque está marcado como privado (visibility = "private").`
  }
  const name = cfg.name ?? lastFolderName(folder)
  if (registry.some((p) => p.name === name)) {
    return `${NOT_IN_PANEL}: já existe um projeto com o nome ${name} no hub. Renomeie em ragx.toml ([project] name) e adicione de novo.`
  }
  return `${NOT_IN_PANEL}: o registro no hub falhou. Rode "ragx project register" nessa pasta para ver o motivo.`
}

/** `QueueDeps.verify`: só `add-project` tem o que conferir depois do último passo. */
export function verifyJob(job: ResolvedJob, d: VerifyDeps): string | null {
  if (job.kind !== 'add-project' || job.folder === undefined) return null
  return verifyAddProject(job.folder, d)
}

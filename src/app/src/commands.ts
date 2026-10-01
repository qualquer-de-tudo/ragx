import type { Route } from './route'
import type { ProjectSnapshot } from './types/ragx-bridge'
import { foldForSearch } from './format'
import { missingEmbeddings } from './state'

/**
 * As únicas tarefas que a paleta pode enfileirar (RAGX-0183). Nada destrutivo: "Reindexar do zero", remover do hub e
 * hooks exigem o `ConfirmButton` e ficam fora. O catálogo do processo principal segue sendo quem aceita o pedido: a
 * paleta só escolhe um `kind` que ele já aceita, para um projeto do snapshot.
 */
export const PALETTE_JOB_KINDS = ['update', 'embed'] as const
export type PaletteJobKind = (typeof PALETTE_JOB_KINDS)[number]

export type CommandAction =
  | { type: 'route'; route: Route }
  | { type: 'job'; kind: PaletteJobKind; projectId: string }
  | { type: 'recheck' }

export interface Command {
  id: string
  label: string
  /** Segunda linha opcional (o caminho do projeto, por exemplo). */
  hint?: string
  disabled?: boolean
  action: CommandAction
}

export const MAX_RESULTS = 8

const PAGES: Array<{ id: string; label: string; route: Route }> = [
  { id: 'go-projects', label: 'Ir para Projetos', route: { page: 'projects' } },
  { id: 'go-activity', label: 'Ir para Atividade', route: { page: 'activity' } },
  { id: 'go-connections', label: 'Ir para Conexões', route: { page: 'connections' } },
  { id: 'go-how', label: 'Ir para Como funciona', route: { page: 'how' } },
]

/** Todos os comandos que existem agora, antes de filtrar. */
export function buildCommands(projects: readonly ProjectSnapshot[]): Command[] {
  const out: Command[] = PAGES.map((p) => ({ id: p.id, label: p.label, action: { type: 'route', route: p.route } }))
  for (const p of projects) {
    out.push({
      id: `open:${p.id}`,
      label: `Abrir ${p.name}`,
      hint: p.path ?? undefined,
      action: { type: 'route', route: { page: 'project', id: p.id } },
    })
  }
  for (const p of projects) {
    out.push({
      id: `update:${p.id}`,
      label: `Atualizar ${p.name}`,
      hint: p.exists ? undefined : 'a pasta do projeto não existe mais',
      disabled: !p.exists,
      action: { type: 'job', kind: 'update', projectId: p.id },
    })
  }
  for (const p of projects) {
    if (missingEmbeddings(p.counts) > 0) {
      out.push({
        id: `embed:${p.id}`,
        label: `Gerar embeddings em ${p.name}`,
        hint: p.exists ? undefined : 'a pasta do projeto não existe mais',
        disabled: !p.exists,
        action: { type: 'job', kind: 'embed', projectId: p.id },
      })
    }
  }
  out.push({ id: 'recheck', label: 'Verificar conexões agora', action: { type: 'recheck' } })
  out.push({ id: 'onboarding', label: 'Refazer a configuração inicial', action: { type: 'route', route: { page: 'onboarding' } } })
  return out
}

/**
 * Filtra sem acento nem maiúscula. Ordem: quem COMEÇA pelo texto (no rótulo ou numa palavra dele), depois quem só o
 * CONTÉM; dentro de cada grupo, a ordem de `buildCommands`. No máximo `MAX_RESULTS`. Sem texto, os primeiros.
 */
export function filterCommands(commands: readonly Command[], query: string): Command[] {
  const q = foldForSearch(query.trim())
  if (q === '') return commands.slice(0, MAX_RESULTS)
  const prefix: Command[] = []
  const inside: Command[] = []
  for (const c of commands) {
    const label = foldForSearch(c.label)
    if (label.startsWith(q) || label.split(/\s+/).some((w) => w.startsWith(q))) prefix.push(c)
    else if (label.includes(q)) inside.push(c)
  }
  return [...prefix, ...inside].slice(0, MAX_RESULTS)
}

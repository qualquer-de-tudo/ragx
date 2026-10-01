import type { ProjectState } from './project-state'

/**
 * Quanto tempo CONTÍNUO em `stale` antes de avisar (RAGX-0191): acima do p95 (37,6 s) da indexação pós-commit, para o
 * aviso só sair quando o índice realmente ficou para trás e o hook não o resolveu sozinho. Decisão desta tarefa.
 */
export const STALE_GRACE_MS = 120_000

export interface ObservedProject {
  id: string
  name: string
  state: ProjectState
}

export interface StaleNotice {
  projectId: string
  name: string
  /** Há quanto tempo está defasado (ms), para o texto "defasado há N min". */
  staleForMs: number
}

/**
 * Decide quando avisar que um índice ficou defasado, uma vez por **episódio**. Episódio = período contínuo em `stale`:
 * `indexing` é neutro (não abre nem fecha); qualquer outro estado fecha. Só notifica depois de `STALE_GRACE_MS`
 * contínuos, uma vez por episódio. O que já estava defasado no primeiro snapshot do processo é semeado sem notificar.
 * Puro: o relógio vem de fora (`now`).
 */
export class StaleNotifier {
  private episodes = new Map<string, { since: number; notified: boolean }>()
  private seeded = false

  observe(projects: readonly ObservedProject[], now: number): StaleNotice[] {
    const out: StaleNotice[] = []
    const alive = new Set(projects.map((p) => p.id))
    for (const id of [...this.episodes.keys()]) if (!alive.has(id)) this.episodes.delete(id)

    for (const p of projects) {
      const ep = this.episodes.get(p.id)
      if (p.state === 'stale') {
        if (!ep) {
          // episódio já aberto no começo do processo: marca como avisado para nunca notificar o que o usuário já via
          this.episodes.set(p.id, { since: now, notified: !this.seeded })
        } else if (!ep.notified && now - ep.since >= STALE_GRACE_MS) {
          ep.notified = true
          out.push({ projectId: p.id, name: p.name, staleForMs: now - ep.since })
        }
      } else if (p.state !== 'indexing') {
        this.episodes.delete(p.id)
      }
    }
    this.seeded = true
    return out
  }

  /** Esquece tudo (a opção foi desligada): ligar de novo semeia como o primeiro snapshot. */
  reset(): void {
    this.episodes.clear()
    this.seeded = false
  }
}

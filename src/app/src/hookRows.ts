import type { ClaudeProfile, ProjectSnapshot } from './types/ragx-bridge'
import type { AutoSetupView } from './hooks/useAutoSetup'

type Tone = 'ok' | 'warn' | 'idle'

export interface HookRow {
  tone: Tone
  title: string
  text: string
}

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`

function nomes(lista: string[], max = 3): string {
  return lista.length <= max ? lista.join(', ') : `${lista.slice(0, max).join(', ')} e mais ${lista.length - max}`
}

/** Os hooks do Claude Code, por perfil onde o RAGX está ligado. Perfil desligado não conta: ligar é decisão da pessoa. */
export function claudeHooksRow(profiles: readonly ClaudeProfile[]): HookRow {
  const title = 'Claude Code'
  if (profiles.length === 0) return { tone: 'idle', title, text: 'Nenhum perfil do Claude Code encontrado nesta máquina.' }
  const ligados = profiles.filter((p) => p.enabled)
  if (ligados.length === 0) {
    return { tone: 'idle', title, text: 'O RAGX está desligado em todos os perfis. Ligue um abaixo e o painel cuida do resto.' }
  }
  const faltando = ligados.filter((p) => !(p.hint && p.touch && p.nudge))
  if (faltando.length === 0) {
    return {
      tone: 'ok',
      title,
      text: `Em dia em ${plural(ligados.length, 'perfil', 'perfis')}: o índice vê o que o agente edita e o lembrete de busca está ativo.`,
    }
  }
  return { tone: 'warn', title, text: `Faltam hooks em ${nomes(faltando.map((p) => p.name))}. O ajuste instala sozinho.` }
}

/** Os hooks de git dos projetos com pasta local e status conhecido. */
export function gitHooksRow(projects: readonly ProjectSnapshot[]): HookRow {
  const title = 'Git'
  const locais = projects.filter((p) => p.path !== null && p.exists && p.hooksInstalled !== null)
  if (locais.length === 0) return { tone: 'idle', title, text: 'Nenhum projeto com índice para conferir ainda.' }
  const sem = locais.filter((p) => p.hooksInstalled === false)
  if (sem.length === 0) {
    return {
      tone: 'ok',
      title,
      text: `Em dia em ${plural(locais.length, 'projeto', 'projetos')}: o índice acompanha troca de branch, commit e merge.`,
    }
  }
  return {
    tone: 'warn',
    title,
    text: `${sem.length} de ${locais.length} sem hooks: ${nomes(sem.map((p) => p.name))}. O ajuste instala sozinho.`,
  }
}

/** O que a última rodada fez, em uma frase; vazio quando não mexeu em nada. */
export function lastRunSummary(state: NonNullable<AutoSetupView['state']>): string {
  const partes: string[] = []
  if (state.claude.installed.length > 0) partes.push(`Claude Code, ${state.claude.installed.join('; ')}`)
  if (state.git.queued.length > 0) partes.push(`Git, hooks em ${state.git.queued.join(', ')}`)
  return partes.length > 0 ? `Instalou: ${partes.join('. ')}.` : 'Nada a instalar.'
}

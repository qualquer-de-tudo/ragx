/**
 * Contador, em memória, dos processos filhos que o painel cria (RAGX-0177).
 *
 * O painel dispara `git`, `ragx`, `docker`... em ciclos (snapshot a cada 5 s, conexões a cada 30 s): o
 * custo mora no NÚMERO e na duração desses filhos, e ninguém o havia medido. Cada ponto de criação de
 * processo chama `countSpawn(executável, ms?)`; o amostrador de `runtime-metrics.ts` tira fotografias e
 * calcula as diferenças. Só soma contadores: nunca guarda argumentos, caminhos de projeto nem saída.
 */

export type SpawnTotals = Record<string, { count: number; ms: number }>

/** Nomes que contam separado; qualquer outro executável vira `outro`. */
const KNOWN = ['git', 'ragx', 'docker', 'tasklist', 'powershell', 'ollama', 'uv', 'job']

let totals: SpawnTotals = {}

/** `C:\Program Files\Git\cmd\git.exe` -> `git`; `/usr/bin/docker` -> `docker`. */
export function executableName(file: string): string {
  const base = file.split(/[\\/]/).pop() ?? file
  const name = base.replace(/\.(exe|cmd|bat|com)$/i, '').toLowerCase()
  return KNOWN.includes(name) ? name : 'outro'
}

/** Registra UM processo criado (e, se já souber, quanto durou). Nunca lança. */
export function countSpawn(file: string, ms = 0): void {
  try {
    const key = executableName(file)
    const entry = (totals[key] ??= { count: 0, ms: 0 })
    entry.count += 1
    entry.ms += Math.max(0, ms)
  } catch {
    // contar nunca pode atrapalhar quem cria o processo
  }
}

/** Soma só a duração (o processo foi contado ao nascer, e terminou agora). */
export function addSpawnDuration(file: string, ms: number): void {
  try {
    const key = executableName(file)
    const entry = (totals[key] ??= { count: 0, ms: 0 })
    entry.ms += Math.max(0, ms)
  } catch {
    // idem
  }
}

/** Cópia dos acumulados, para o amostrador calcular a diferença entre duas amostras. */
export function snapshot(): SpawnTotals {
  return Object.fromEntries(Object.entries(totals).map(([k, v]) => [k, { ...v }]))
}

/** O que mudou entre duas fotografias (`depois` - `antes`), só dos executáveis que apareceram. */
export function diffSpawns(antes: SpawnTotals, depois: SpawnTotals): SpawnTotals {
  const out: SpawnTotals = {}
  for (const [key, now] of Object.entries(depois)) {
    const before = antes[key] ?? { count: 0, ms: 0 }
    const count = now.count - before.count
    const ms = now.ms - before.ms
    if (count > 0 || ms > 0) out[key] = { count, ms }
  }
  return out
}

/** Para teste. */
export function resetSpawnCounter(): void {
  totals = {}
}

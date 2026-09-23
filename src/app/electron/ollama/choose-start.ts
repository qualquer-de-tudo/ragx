import type { OllamaEnvironment } from '../../src/types/ragx-bridge'

export type StartMode = 'docker' | 'native'

/** O lado existe na máquina para ser iniciado: container criado ou Ollama local instalado. */
function available(env: OllamaEnvironment, mode: StartMode | null): boolean {
  if (mode === 'docker') return env.container.exists
  if (mode === 'native') return env.native.installed
  return false
}

/**
 * Qual Ollama o "Iniciar" liga. Uma função só, usada pelo catálogo (o que a
 * tarefa `ollama-start` roda) e pela checagem de conexões (o texto do botão),
 * para o botão nunca prometer um lado e a tarefa ligar o outro.
 *
 * Ordem: o modo preferido (a última troca do usuário) se existir na máquina;
 * depois a recomendação; depois o container, se existir; depois o Ollama
 * local, se instalado. `null`: não há nada para iniciar.
 */
export function chooseStartMode(env: OllamaEnvironment, preferred: StartMode | null): StartMode | null {
  const candidates: Array<StartMode | null> = [preferred, env.recommendation.mode, 'docker', 'native']
  return candidates.find((m): m is StartMode => available(env, m)) ?? null
}

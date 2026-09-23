import { randomUUID } from 'node:crypto'

/** Mais que suficiente para uma sessão do painel; limita a memória gasta por uma sessão longa (Fix round 1). */
const MAX_TOKENS = 500

/**
 * Mapa opaco token -> caminho de pasta, em memória do processo principal. O
 * renderer nunca vê um caminho de disco de verdade: só recebe o token (Task
 * 6, `pickFolder`/`discover`) e manda ele de volta como argumento
 * (`add-project`), nunca um caminho livre. Cada `issue()` gera um token
 * novo, mesmo para o mesmo caminho - não há dedupe por caminho.
 *
 * Guarda no máximo os `MAX_TOKENS` mais recentes - `Map` preserva ordem de
 * inserção, então o mais antigo é sempre a primeira chave.
 */
export class FolderTokens {
  private readonly byToken = new Map<string, string>()

  issue(path: string): string {
    const token = randomUUID()
    this.byToken.set(token, path)
    if (this.byToken.size > MAX_TOKENS) {
      const oldest = this.byToken.keys().next().value
      if (oldest !== undefined) this.byToken.delete(oldest)
    }
    return token
  }

  get(token: string): string | undefined {
    return this.byToken.get(token)
  }
}

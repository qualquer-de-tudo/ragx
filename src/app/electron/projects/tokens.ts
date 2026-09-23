import { randomUUID } from 'node:crypto'

/**
 * Mapa opaco token -> caminho de pasta, em memória do processo principal. O
 * renderer nunca vê um caminho de disco de verdade: só recebe o token (Task
 * 6, `pickFolder`/`discover`) e manda ele de volta como argumento
 * (`add-project`), nunca um caminho livre. Cada `issue()` gera um token
 * novo, mesmo para o mesmo caminho - não há dedupe por caminho.
 */
export class FolderTokens {
  private readonly byToken = new Map<string, string>()

  issue(path: string): string {
    const token = randomUUID()
    this.byToken.set(token, path)
    return token
  }

  get(token: string): string | undefined {
    return this.byToken.get(token)
  }
}

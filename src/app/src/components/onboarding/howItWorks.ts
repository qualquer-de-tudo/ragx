/**
 * Texto do passo 1 do onboarding, repetido na tela "Como funciona".
 * Parágrafos curtos, sem travessão.
 */
export const HOW_IT_WORKS_TITLE = 'Como o RAGX funciona'

export const HOW_IT_WORKS: readonly string[] = [
  'O RAGX lê seus projetos aqui mesmo, na sua máquina, e guarda o que encontra em pedaços pequenos (chunks) com um resumo numérico de cada um (embeddings).',
  'Quando o Claude Code precisa entender o projeto, ele pergunta ao RAGX pelo MCP em vez de abrir arquivo por arquivo. Chega só o trecho que importa.',
  'Arquivos com segredos, como .env e chaves, são bloqueados antes de entrar no índice.',
  'Os hooks de git mantêm o índice na branch em que você está: ao trocar de branch, commitar ou fazer pull, o RAGX atualiza sozinho em segundo plano.',
  'Os embeddings são gerados pelo Ollama, que roda no Docker.',
]

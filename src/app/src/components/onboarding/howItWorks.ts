/**
 * Texto do "Como funciona": o passo 1 do onboarding (`HOW_IT_WORKS`) e a tela da barra lateral (as listas abaixo).
 * Parágrafos curtos, sem travessão.
 */
export const HOW_IT_WORKS_TITLE = 'Como o RAGX funciona'

export const HOW_IT_WORKS: readonly string[] = [
  'O RAGX lê seus projetos aqui mesmo, na sua máquina, e guarda o que encontra em pedaços pequenos (chunks) com um resumo numérico de cada um (embeddings).',
  'Claude Code, Codex, Gemini CLI, Cursor e Windsurf podem consultar o RAGX pelo MCP. O agente recebe trechos relevantes do projeto, com as fontes, dentro de um limite de tokens.',
  'Arquivos com segredos, como .env e chaves, são bloqueados antes de entrar no índice.',
  'Os hooks de git mantêm o índice na branch em que você está: ao trocar de branch, commitar ou fazer pull, o RAGX atualiza sozinho em segundo plano. Um hook no Claude Code avisa de cada arquivo que o agente edita.',
  'Os embeddings são gerados pelo Ollama, que roda no Docker ou direto no seu computador.',
]

export interface HowStep {
  title: string
  text: string
}

/** O caminho do dado, na ordem em que acontece: aqui a sequência é real, então a tela a numera. */
export const HOW_STEPS: readonly HowStep[] = [
  { title: 'Seu código', text: 'Os arquivos do projeto ficam onde estão, na sua máquina.' },
  { title: 'Security Gate', text: 'Segredos como .env e chaves são barrados antes de qualquer leitura.' },
  { title: 'Índice', text: 'Pedaços pequenos (chunks) e um resumo numérico de cada um (embeddings), gerados pelo Ollama.' },
  { title: 'MCP', text: 'Conecta Claude Code, Codex, Gemini CLI e outros agentes ao índice do seu projeto.' },
  { title: 'Seu agente', text: 'Recebe os trechos relevantes com arquivo e linhas para trabalhar com contexto.' },
]

export interface HowKeep {
  title: string
  text: string
}

/** O que mantém o índice em dia sem você fazer nada. */
export const HOW_KEEPS: readonly HowKeep[] = [
  {
    title: 'Ao trocar de branch, commitar ou fazer merge',
    text: 'Hooks de git reindexam em segundo plano, só o que mudou.',
  },
  {
    title: 'A cada arquivo que o agente edita',
    text: 'Um hook no Claude Code avisa o RAGX, que reindexa só aquele arquivo. A próxima busca já enxerga a edição.',
  },
  {
    title: 'Os próprios hooks',
    text: 'O painel instala e confere os dois tipos sozinho. Em Conexões você vê o estado e pode desligar.',
  },
]

/** Onde ficam os dados. */
export const HOW_LOCAL: readonly string[] = [
  'O índice de cada projeto fica na pasta .ragx dele, no seu computador.',
  'O Ollama roda localmente: nenhum trecho do seu código sai da máquina para gerar embeddings.',
  'O RAGX nunca guarda a sua pergunta: o log registra só qual ferramenta foi chamada e quantos tokens economizou.',
]

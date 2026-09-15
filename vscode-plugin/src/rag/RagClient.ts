/**
 * A camada que isola o plugin do RAGX.
 *
 * Tudo que a UI sabe está nesta interface. Trocar MCP por HTTP, por uma API
 * Python embutida ou por qualquer outra coisa é escrever uma implementação
 * nova — nenhuma tela muda.
 *
 * Duas regras valem para toda implementação:
 *
 *   1. **Erro é dado.** Nada aqui lança por falha do RAGX; devolve
 *      `{ ok: false, error }`. Uma UI que precisa de try/catch em cada chamada
 *      acaba com telas em branco quando alguém esquece um.
 *   2. **O RAGX é a fonte de verdade da segurança.** O plugin não decide o que
 *      pode ser mostrado: se o RAGX não devolve, não existe.
 */

import type {
  AgentInfo,
  ChunkInfo,
  ContextPack,
  DictionarySection,
  DocumentInfo,
  EntityDetail,
  FileKnowledge,
  GraphSlice,
  HealthCheck,
  KnowledgeStats,
  MonitorSnapshot,
  ProjectInfo,
  RagResult,
  RequestAnalysis,
  SearchFilters,
  SearchMode,
  SearchResponse,
  SecurityStatus,
  SourcesOverview,
  TaskDetail,
  TaskGraph,
  TaskInfo,
  TaskPanel,
} from './types';

export interface RagClient {
  readonly transport: 'mcp' | 'cli';

  connect(): Promise<RagResult<ProjectInfo>>;
  dispose(): Promise<void>;

  stats(): Promise<RagResult<KnowledgeStats>>;
  health(): Promise<RagResult<HealthCheck[]>>;

  search(
    query: string,
    mode: SearchMode,
    limit: number,
    filters?: SearchFilters,
    signal?: AbortSignal,
  ): Promise<RagResult<SearchResponse>>;

  /** Vizinhança de UMA entidade. Nunca o grafo inteiro — ver §12 do pedido. */
  graph(entity: string, depth: number, maxNodes: number): Promise<RagResult<GraphSlice>>;
  entity(name: string): Promise<RagResult<EntityDetail>>;

  /**
   * As origens do conhecimento: este projeto, as fontes base e o hub.
   *
   * Existe porque um índice pode conter três coisas diferentes ao mesmo tempo,
   * e tratá-las como uma só faz a pessoa acreditar que o repositório contém
   * algo que na verdade veio de fora dele.
   */
  sources(): Promise<RagResult<SourcesOverview>>;

  dictionary(): Promise<RagResult<DictionarySection[]>>;
  documents(query?: string, limit?: number): Promise<RagResult<DocumentInfo[]>>;
  fileKnowledge(relPath: string): Promise<RagResult<FileKnowledge>>;
  /** Conteúdo completo de um chunk. A busca devolve recorte; isto devolve tudo. */
  chunk(chunkId: string): Promise<RagResult<ChunkInfo>>;

  buildContext(query: string, tokens: number): Promise<RagResult<ContextPack>>;

  /**
   * Orquestração — LEITURA apenas.
   *
   * Reivindicar, reportar e mudar estado de tarefa são operações de escrita, e
   * elas continuam na CLI e no agente. Uma tela de exploração que também
   * executa trabalho seria uma forma silenciosa de dar ao plugin um poder que
   * o servidor sobe desligado por padrão.
   */
  tasks(project?: string, status?: string): Promise<RagResult<TaskInfo[]>>;
  task(taskId: string): Promise<RagResult<TaskDetail>>;
  taskGraph(project?: string): Promise<RagResult<TaskGraph>>;
  taskPanel(): Promise<RagResult<TaskPanel>>;
  /** Classifica um pedido sem criar nada. O `--apply` não passa por aqui. */
  analyzeRequest(request: string): Promise<RagResult<RequestAnalysis>>;

  security(): Promise<RagResult<SecurityStatus>>;
  monitor(): Promise<RagResult<MonitorSnapshot>>;
  agents(): Promise<RagResult<AgentInfo[]>>;

  /** Sync incremental. Nunca reindexação completa — ver §48 do pedido. */
  sync(): Promise<RagResult<{ indexed: number; removed: number; warnings: string[] }>>;
}

export function fail<T>(code: string, message: string): RagResult<T> {
  return { ok: false, error: { code, message } };
}

export function done<T>(data: T): RagResult<T> {
  return { ok: true, data };
}

/**
 * Repassa uma FALHA trocando só o parâmetro de tipo.
 *
 * Todo uso está num ramo onde `ok === false` — não existe dado para converter,
 * e um `as RagResult<X>` ali seria mentira para o compilador. Isto diz o que
 * realmente acontece: o erro sobe, o tipo acompanha.
 */
export function propagate<T>(r: RagResult<unknown>): RagResult<T> {
  return {
    ok: false,
    error: r.error ?? { code: 'error', message: 'falha sem detalhe' },
  };
}

/**
 * Primeira linha, curta, e nunca um traceback.
 *
 * O ramo padrão do `humanize` repassava `error.message` inteiro — e a mensagem
 * de uma falha do RAGX pode ser um traceback de Python. Um teste pegou isso:
 * stack trace na tela é exatamente o que a §39 proíbe. O detalhe continua
 * inteiro no Output.
 */
function resumir(mensagem: string): string {
  const primeira = (mensagem || '').split('\n')[0]?.trim() ?? '';
  if (!primeira || /traceback|most recent call last|^\s*File "/i.test(primeira)) {
    return 'O RAGX devolveu um erro inesperado. O detalhe está nos logs.';
  }
  return primeira.length > 240 ? primeira.slice(0, 237) + '…' : primeira;
}

/**
 * Traduz a falha para linguagem de quem está lendo, com uma saída.
 *
 * Stack trace na tela é confissão de que ninguém pensou no caso (§39). O
 * detalhe vai para o Output; aqui fica o que a pessoa pode fazer a respeito.
 */
export function humanize(error: { code: string; message: string }): {
  title: string;
  reason: string;
  actions: Array<'retry' | 'logs' | 'settings' | 'init' | 'sync'>;
} {
  switch (error.code) {
    case 'not_found':
      return {
        title: 'Não encontrado no índice',
        reason:
          'Isto pode significar que o arquivo nunca foi indexado — ou que o ' +
          'Security Gate o bloqueou por conter segredo. Nos dois casos, a ' +
          'resposta é a resposta.',
        actions: ['sync', 'logs'],
      };
    case 'spawn_failed':
      return {
        title: 'Não foi possível iniciar o RAGX',
        reason:
          `O comando configurado não pôde ser executado. Verifique se o RAGX ` +
          `está instalado e no PATH, ou aponte o caminho completo em ` +
          `"ragx.command".`,
        actions: ['settings', 'retry', 'logs'],
      };
    case 'no_project':
      return {
        title: 'Nenhum projeto RAGX neste workspace',
        reason:
          'Não encontrei `ragx.toml`, `knowledge/` nem `.ragx/`. Rode ' +
          '`ragx init` na raiz do projeto para começar.',
        actions: ['init', 'retry'],
      };
    case 'rate_limited':
      return {
        title: 'Muitas consultas seguidas',
        reason: 'O RAGX limitou a taxa de chamadas. Aguarde alguns segundos.',
        actions: ['retry'],
      };
    case 'too_large':
      return {
        title: 'Resposta grande demais',
        reason:
          'O RAGX recusa resposta acima do limite em vez de truncar em ' +
          'silêncio. Reduza o limite de resultados ou o orçamento de tokens.',
        actions: [],
      };
    case 'timeout':
      return {
        title: 'O RAGX demorou demais',
        reason:
          'A primeira busca carrega o modelo de embeddings e pode levar alguns ' +
          'segundos. Se voltar a acontecer, veja os logs.',
        actions: ['retry', 'logs'],
      };
    case 'write_disabled':
      return {
        title: 'Servidor em modo somente-leitura',
        reason:
          'Esta operação escreve no índice. Suba o servidor com ' +
          '`ragx mcp serve --write`.',
        actions: ['settings', 'logs'],
      };
    default:
      return {
        title: 'Falha ao falar com o RAGX',
        reason: resumir(error.message),
        actions: ['retry', 'logs'],
      };
  }
}

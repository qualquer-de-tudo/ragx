/**
 * Protocolo entre a extensão e a webview.
 *
 * Tipado dos dois lados, sem `any` (§33). Toda requisição carrega um `id`, e a
 * resposta devolve o mesmo — sem isso, duas buscas rápidas em sequência
 * chegariam fora de ordem e a UI mostraria o resultado da consulta anterior
 * como se fosse da atual.
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
  RequestAnalysis,
  SearchFilters,
  SearchMode,
  SearchResponse,
  SecurityStatus,
  SourcesOverview,
  SystemState,
  TaskDetail,
  TaskGraph,
  TaskInfo,
  TaskPanel,
} from './rag/types';

export interface UiSettings {
  searchMode: SearchMode;
  graphMaxDepth: number;
  maxVisibleNodes: number;
  contextTokenBudget: number;
}

/**
 * Onde esta webview esta' hospedada.
 *
 * A UI precisa saber: na barra lateral ha' ~300px e faz sentido oferecer
 * "abrir em tela cheia"; no editor esse botao nao existe, e o espaco extra
 * vira uma segunda coluna de detalhe em vez de scroll.
 */
export type HostMode = 'sidebar' | 'editor';

/** Webview → extensão. */
export type WebviewMessage =
  | { type: 'ready'; id: string }
  | { type: 'search'; id: string; query: string; mode: SearchMode; limit: number; filters?: SearchFilters }
  | { type: 'cancelSearch'; id: string }
  | { type: 'getStats'; id: string }
  | { type: 'getHealth'; id: string }
  | { type: 'getGraph'; id: string; entity: string; depth: number }
  | { type: 'getEntity'; id: string; name: string }
  | { type: 'getDictionary'; id: string }
  | { type: 'getDocuments'; id: string; query?: string }
  | { type: 'getFileKnowledge'; id: string; path: string }
  | { type: 'getChunk'; id: string; chunkId: string }
  | { type: 'buildContext'; id: string; query: string; tokens: number }
  | { type: 'getSecurity'; id: string }
  | { type: 'getMonitor'; id: string }
  | { type: 'getAgents'; id: string }
  | { type: 'getSources'; id: string }
  | { type: 'getTasks'; id: string; project?: string; status?: string }
  | { type: 'getTask'; id: string; taskId: string }
  | { type: 'getTaskGraph'; id: string; project?: string }
  | { type: 'getTaskPanel'; id: string }
  | { type: 'analyzeRequest'; id: string; request: string }
  | { type: 'sync'; id: string }
  | { type: 'reconnect'; id: string }
  | { type: 'openFile'; id: string; path: string; line?: number; endLine?: number }
  | { type: 'openEditor'; id: string; page?: PageId }
  | { type: 'copy'; id: string; text: string }
  | { type: 'saveContext'; id: string; markdown: string }
  | { type: 'openLogs'; id: string }
  | { type: 'openSettings'; id: string }
  | { type: 'runCommand'; id: string; command: string };

/** Extensão → webview. */
export type ExtensionMessage =
  | { type: 'state'; state: SystemState; project?: ProjectInfo; message?: string; host: HostMode }
  | { type: 'settings'; settings: UiSettings }
  | { type: 'navigate'; page: PageId; payload?: Record<string, string> }
  | { type: 'result'; id: string; ok: true; payload: ResultPayload }
  | { type: 'result'; id: string; ok: false; error: UiError };

export type PageId =
  | 'overview'
  | 'search'
  | 'graph'
  | 'dictionary'
  | 'documents'
  | 'sources'
  | 'context'
  | 'tasks'
  | 'agents'
  | 'monitor'
  | 'security';

export interface UiError {
  code: string;
  title: string;
  reason: string;
  actions: Array<'retry' | 'logs' | 'settings' | 'init' | 'sync'>;
}

export type ResultPayload =
  | { kind: 'stats'; stats: KnowledgeStats }
  | { kind: 'health'; checks: HealthCheck[] }
  | { kind: 'search'; response: SearchResponse }
  | { kind: 'graph'; graph: GraphSlice }
  | { kind: 'entity'; entity: EntityDetail }
  | { kind: 'dictionary'; sections: DictionarySection[] }
  | { kind: 'documents'; documents: DocumentInfo[] }
  | { kind: 'fileKnowledge'; knowledge: FileKnowledge }
  | { kind: 'chunk'; chunk: ChunkInfo }
  | { kind: 'context'; pack: ContextPack }
  | { kind: 'security'; security: SecurityStatus }
  | { kind: 'monitor'; monitor: MonitorSnapshot }
  | { kind: 'agents'; agents: AgentInfo[] }
  | { kind: 'sources'; overview: SourcesOverview }
  | { kind: 'tasks'; tasks: TaskInfo[] }
  | { kind: 'task'; task: TaskDetail }
  | { kind: 'taskGraph'; graph: TaskGraph }
  | { kind: 'taskPanel'; panel: TaskPanel }
  | { kind: 'analysis'; analysis: RequestAnalysis }
  | { kind: 'sync'; indexed: number; removed: number; warnings: string[] }
  | { kind: 'ack' };

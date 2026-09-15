/**
 * Contratos do RAGX vistos pelo plugin.
 *
 * São os MESMOS tipos usados pela extensão e pela webview — um único arquivo,
 * importado dos dois lados. Duplicar as formas produziria o bug clássico
 * "funciona no host, quebra na UI" na primeira vez que um campo mudar.
 *
 * Nada aqui espelha o interior do RAGX: só o que as ferramentas devolvem.
 */

export type ConnectionState =
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'notFound'
  | 'error';

export type SystemState =
  | 'ready'
  | 'indexing'
  | 'syncing'
  | 'outdated'
  | 'error'
  | 'warning'
  | 'securityBlocked'
  | 'disconnected';

export type SearchMode = 'hybrid' | 'semantic' | 'keyword';

/** Envelope de toda resposta do RAGX. Erro é dado, não exceção. */
export interface RagResult<T> {
  ok: boolean;
  data?: T;
  error?: { code: string; message: string };
}

export interface ProjectInfo {
  name: string;
  root: string;
  /** Como a conexão foi estabelecida — aparece na UI para diagnóstico. */
  transport: 'mcp' | 'cli';
  ragxVersion?: string;
}

export interface KnowledgeStats {
  initialized: boolean;
  documents: number;
  chunks: number;
  embeddings: number;
  entities: number;
  relations: number;
  securityEvents: number;
  byLang: Record<string, number>;
  embeddingModel?: { id: string; dim: number; versionedDim: number };
  lastRun?: {
    mode: string;
    startedAt?: string;
    finishedAt?: string;
    filesSeen?: number;
    indexed?: number;
    blocked?: number;
    durationMs?: number;
  };
}

export interface SearchHit {
  chunkId: string;
  project: string;
  documentPath: string;
  symbol: string | null;
  headingPath: string | null;
  kind: string;
  lines: [number, number];
  score: number;
  content: string;
  /** `keyword` significa que o termo literal existe. Vale muito mais que `semantic`. */
  matchedBy: string[];
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  degraded: string | null;
  timingsMs?: Record<string, number>;
  results: SearchHit[];
}

export interface SearchFilters {
  lang?: string;
  kind?: string;
  pathGlob?: string;
  minScore?: number;
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  qualifiedName?: string | null;
  documentPath?: string | null;
  summary?: string | null;
  /** Quantos vizinhos existem além dos já carregados. Move a expansão progressiva. */
  degree?: number;
  expanded?: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
}

export interface GraphSlice {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** `true` quando o RAGX cortou por limite — a UI precisa DIZER isso. */
  truncated?: boolean;
}

export interface EntityDetail {
  entity: GraphNode;
  relations: Array<{
    type: string;
    direction: 'out' | 'in';
    target: string;
    targetId?: string;
  }>;
  sources: Array<{ path: string; line?: number }>;
}

export interface DictionarySection {
  id: string;
  label: string;
  items: DictionaryItem[];
}

export interface DictionaryItem {
  name: string;
  description?: string;
  evidence?: string[];
  related?: string[];
}

export interface DocumentInfo {
  path: string;
  lang: string | null;
  kind: string | null;
  title: string | null;
  chunks: number;
  redacted: boolean;
}

export interface ChunkInfo {
  chunkId: string;
  ordinal: number;
  kind: string;
  symbol: string | null;
  headingPath: string | null;
  lines: [number, number];
  tokens: number;
  content?: string;
}

export interface ContextFragment {
  chunkId: string;
  documentPath: string;
  lines: [number, number];
  tokens: number;
  content: string;
  symbol?: string | null;
}

export interface ContextPack {
  query: string;
  estimatedTokens: number;
  budget: number;
  fragments: ContextFragment[];
  sources: string[];
  markdown?: string;
}

export interface SecurityStatus {
  gateActive: boolean;
  policy: string;
  rules: number;
  blockedFiles: number;
  redactedFiles: number;
  /**
   * Motivos agregados. NUNCA o conteúdo, e nunca o caminho de um arquivo
   * bloqueado: a lista de onde estão os segredos é, ela mesma, um segredo.
   */
  reasons: Array<{ rule: string; count: number }>;
  ignoreFiles: string[];
  indexedSecrets: number;
  embeddedSecrets: number;
}

export interface HealthCheck {
  name: string;
  status: 'ok' | 'warn' | 'error';
  detail?: string;
}

export interface AgentInfo {
  name: string;
  state: 'ready' | 'training' | 'stale' | 'unknown';
  chunks?: number;
  skills?: number;
  rules?: number;
  examples?: number;
  coverage?: number;
  gaps?: number;
  sources?: string[];
}

export interface ActivityEntry {
  at: string;
  kind: string;
  message: string;
}

export interface MonitorSnapshot {
  stats: KnowledgeStats;
  activity: ActivityEntry[];
  tasks?: Record<string, number>;
  scheduler?: { total: number; enabled: number; next?: string | null };
}

export interface FileKnowledge {
  path: string;
  indexed: boolean;
  reason?: string;
  chunks: ChunkInfo[];
  entities: string[];
  document?: DocumentInfo;
}

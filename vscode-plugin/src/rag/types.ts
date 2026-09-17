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
  /**
   * `current` (só este projeto), `all` ou `project:<nome>`.
   *
   * O índice pode conter conhecimento de várias origens ao mesmo tempo — este
   * projeto, fontes base compartilhadas e outros projetos do hub. Sem escopo,
   * "buscar" mistura as três e a resposta deixa de dizer de onde veio.
   */
  scope?: string;
}

// ── origens do conhecimento ─────────────────────────────────────────────
/**
 * De onde vem cada pedaço do índice.
 *
 * Três origens distintas, que NÃO devem ser lidas como a mesma coisa:
 *
 *   - `project`: o repositório aberto. É o que o RAGX indexa e reindexa.
 *   - `base`: conhecimento compartilhado (`@base/<nome>/…`), instalado na
 *     máquina e declarado por este projeto. Vive fora do repositório.
 *   - `peer`: outro projeto registrado no hub local. Pode nem estar clonado —
 *     o que se sabe dele vem da superfície pública que ele publicou.
 */
export type SourceKind = 'project' | 'base' | 'peer';

export interface KnowledgeSource {
  id: string;
  kind: SourceKind;
  name: string;
  /** URL do git ou caminho local, para fonte base. */
  origin?: string;
  commit?: string;
  enabled: boolean;
  /** Fonte base: este projeto a DECLARA em `[base] sources`? */
  declared?: boolean;
  /** Projeto do hub: existe em disco nesta máquina? */
  cloned?: boolean;
  visibility?: string;
  status?: string;
  path?: string;
  /**
   * Contagens quando o RAGX sabe. `undefined` significa "não sei", e a UI
   * precisa dizer isso em vez de mostrar zero — zero é uma afirmação.
   */
  documents?: number;
  chunks?: number;
  entities?: number;
  /** Prefixo que isola esta origem numa listagem de documentos. */
  pathPrefix?: string;
  /** Escopo correspondente na busca. */
  scope?: string;
}

export interface SourcesOverview {
  sources: KnowledgeSource[];
  integrations: Array<{ from: string; to: string; kind: string; name?: string }>;
  unresolved: string[];
  divergences: string[];
  /** Sem hub, só existem este projeto e as fontes base — e isso é o normal. */
  hubAvailable: boolean;
}

/**
 * De onde veio a informação do grafo.
 *
 * `structural` saiu do AST — o RAGX leu a declaração. `reference` e `semantic`
 * são inferência: heurística sobre texto e, no caso de `semantic`, modelo.
 * A UI mostra a diferença porque "A importa B" e "A talvez mencione B" não
 * merecem o mesmo traço na tela.
 */
export type GraphProvenance = 'structural' | 'reference' | 'semantic';

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
  confidence?: number;
  provenance?: GraphProvenance;
}

/**
 * Aresta orientada `source → target`, em IDs de entidade.
 *
 * Os nomes seguem o que a renderização precisa; o servidor chama os mesmos
 * campos de `src`/`dst`, como a tabela `relations`. A tradução acontece num
 * lugar só — ver `McpClient.graph()` — e há teste de contrato dos dois lados.
 */
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  confidence?: number;
  provenance?: GraphProvenance;
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
    /** Nome do nó do OUTRO lado — o que a lista de relações mostra. */
    target: string;
    targetId?: string;
    confidence?: number;
    provenance?: GraphProvenance;
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
  /** Só vem quando o chunk é pedido inteiro; a listagem por documento omite. */
  content?: string;
  documentPath?: string;
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

// ── orquestração (Fase 13) ──────────────────────────────────────────────
/**
 * Os estados vêm do RAGX, não desta lista.
 *
 * O tipo é aberto (`| string`) de propósito: um estado novo no servidor não
 * pode fazer a tela sumir. A UI trata o que conhece e mostra o resto como
 * texto — degradar é melhor que quebrar.
 */
export type TaskStatus =
  | 'pending' | 'ready' | 'queued' | 'running' | 'blocked'
  | 'completed' | 'failed' | 'cancelled' | 'needs_review'
  | (string & {});

export interface TaskInfo {
  id: string;
  projectId: string;
  title: string;
  status: TaskStatus;
  priority: string;
  track: string;
  type: string;
  requiresApproval: boolean;
  acceptanceCriteria: string[];
  filesScope: string[];
  retryCount: number;
}

export interface TaskDetail {
  task: TaskInfo & {
    description?: string;
    testRequirements?: string[];
    securityRequirements?: string[];
    createdAt?: string;
    updatedAt?: string;
    leaseExpiresAt?: string;
    assignee?: string;
  };
  dependencies: Array<{ id: string; title?: string; status?: TaskStatus }>;
  dependents: Array<{ id: string; title?: string; status?: TaskStatus }>;
  lastResult?: {
    status?: string;
    summary?: string;
    filesChanged?: string[];
    checks?: Array<{ name: string; passed: boolean; detail?: string }>;
  };
}

export interface TaskGraph {
  nodes: Array<{ id: string; title: string; status: TaskStatus; track?: string }>;
  edges: Array<{ from: string; to: string; kind: string }>;
}

export interface TaskPanel {
  /** Contagem por estado. Vazio significa "nenhuma tarefa", não "erro". */
  counts: Record<string, number>;
  projects: Array<{ id: string; name: string; status: string }>;
  scheduler?: { total: number; enabled: number; next?: string | null };
  /** O painel responde mesmo com o banco de orquestração ausente — e diz isso. */
  unavailable?: string;
}

/**
 * O que o Task Analyzer decidiu — sem escrever nada.
 *
 * `classification` é o veredito: executar agora ou documentar e decompor
 * antes. O plugin só LÊ isso; aplicar o plano continua sendo `ragx task plan
 * --apply`, que escreve, e escrita não sai de uma tela de exploração.
 */
export interface RequestAnalysis {
  classification: string;
  complexity: string;
  strategy: string;
  /** Total EFETIVO — o que decidiu, que pode diferir do bruto por redução. */
  total: number;
  rawTotal: number;
  confidence: number;
  reasoning: string;
  requiresDocumentation: boolean;
  requiresDecomposition: boolean;
  requiresApproval: boolean;
  /** As sete dimensões, cada uma de 0 a 100. */
  scores: Record<string, number>;
  matchedSignals: string[];
  risks: string[];
  dependencies: string[];
  overriddenBy?: string;
  overrideReason?: string;
}

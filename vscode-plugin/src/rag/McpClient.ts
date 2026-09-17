/**
 * Transporte MCP por stdio — o padrão.
 *
 * A razão é medida, não estética: a primeira busca do RAGX carrega o modelo de
 * embeddings e leva ~2s. Num processo quente isso acontece uma vez; com um
 * processo por consulta, acontece em TODA consulta, e a busca incremental fica
 * inutilizável.
 *
 * O servidor sobe em modo LEITURA por padrão. Escrita (reindexar, sincronizar)
 * é habilitada pela configuração e usada só nos comandos que a pedem.
 */

import { ChildProcess } from 'node:child_process';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

import {
  toAnalysis,
  toChunk,
  toDocument,
  toEdge,
  toTier as tierOf,
  toSources,
  toTask,
  toTaskDetail,
  toTaskGraph,
  toTaskPanel,
} from './parse';
import { done, fail, propagate, type RagClient } from './RagClient';
import type {
  AgentInfo,
  ChunkInfo,
  ContextPack,
  DictionaryItem,
  DictionarySection,
  DocumentInfo,
  EntityDetail,
  FileKnowledge,
  GraphEdge,
  GraphNode,
  GraphSlice,
  HealthCheck,
  KnowledgeStats,
  MonitorSnapshot,
  ProjectInfo,
  RagResult,
  RequestAnalysis,
  SearchFilters,
  SearchHit,
  SearchMode,
  SearchResponse,
  SecurityStatus,
  SourcesOverview,
  TaskDetail,
  TaskGraph,
  TaskInfo,
  TaskPanel,
} from './types';

/**
 * Teto de `limit` do `SearchRequest` do RAGX (`MAX_LIMIT` em `mcp/tools.py`).
 * O servidor RECUSA acima disso com ValidationError em vez de truncar, então
 * quem pede mais do que cabe não recebe menos: não recebe nada.
 */
const MAX_SEARCH_LIMIT = 50;

export interface McpOptions {
  command: string;
  args: string[];
  cwd: string;
  /** Escrita desligada por padrão: o plugin é um explorador, não um indexador. */
  write?: boolean;
  timeoutMs?: number;
  log?: (line: string) => void;
  /**
   * Chamado quando o processo do RAGX cai SOZINHO — crash do Python, pipe
   * fechado, `kill` de fora. Sem isto, a extensão só descobria na próxima
   * consulta, que falhava com um erro de transporte sem explicação; o estado
   * continuava "Ready" enquanto não havia mais ninguém do outro lado.
   *
   * Não dispara em `dispose()`: desligar de propósito não é queda.
   */
  onCrash?: (motivo: string) => void;
}

/**
 * Quanto tempo levou cada etapa até o RAGX ficar pronto.
 *
 * Existe para responder "por que demorou?" com medida em vez de palpite. O
 * gargalo medido neste projeto é `spawnBootHandshakeMs` — o boot do Python e
 * o import do SDK de MCP —, e não o transporte nem as consultas.
 */
export interface ConnectTimings {
  spawnBootHandshakeMs: number;
  listToolsMs: number;
  handshakeMs: number;
  totalMs: number;
}

type Json = Record<string, unknown>;

const DEFAULT_TIMEOUT = 120_000;

/** Injetada pelo esbuild a partir do package.json. Nos testes, que não
 *  passam pelo bundler, `typeof` evita o ReferenceError e sobra `dev`. */
declare const __RAGX_VERSION__: string;
const VERSAO = typeof __RAGX_VERSION__ === 'string' ? __RAGX_VERSION__ : 'dev';

export class McpRagClient implements RagClient {
  readonly transport = 'mcp' as const;

  private client?: Client;
  private child?: ChildProcess;
  private options: McpOptions;
  private tools = new Set<string>();
  /** Nome do projeto conectado; usado para separar o que é dele do que não é. */
  private projeto = 'este projeto';
  /** `true` entre um `connect()` que deu certo e o fim da conexão. */
  private vivo = false;
  private timings?: ConnectTimings;

  constructor(options: McpOptions) {
    this.options = options;
  }

  private log(line: string): void {
    this.options.log?.(line);
  }

  async connect(): Promise<RagResult<ProjectInfo>> {
    const t0 = Date.now();
    let marca = t0;
    const desde = () => {
      const agora = Date.now();
      const dt = agora - marca;
      marca = agora;
      return dt;
    };

    try {
      const args = [...this.options.args];
      if (this.options.write && !args.includes('--write')) args.push('--write');
      if (!this.options.write && !args.includes('--read-only')) args.push('--read-only');

      const transport = new StdioClientTransport({
        command: this.options.command,
        args,
        cwd: this.options.cwd,
        // O servidor escreve avisos em stderr (carga de modelo, por exemplo).
        // Eles vão para o Output, não para a UI.
        stderr: 'pipe',
      });

      this.client = new Client(
        { name: 'ragx-vscode', version: VERSAO },
        { capabilities: {} },
      );
      await this.client.connect(transport);
      const spawnBootHandshakeMs = desde();

      const listed = await this.client.listTools();
      this.tools = new Set(listed.tools.map((t) => t.name));
      const listToolsMs = desde();

      const stderr = (transport as unknown as { stderr?: NodeJS.ReadableStream }).stderr;
      stderr?.on('data', (buf: Buffer) => this.log(`[ragx] ${buf.toString().trim()}`));

      const playbook = await this.call<Json>('get_playbook', {});
      const handshakeMs = desde();
      const project =
        (playbook.ok && (playbook.data?.project as string)) || 'projeto';
      this.projeto = project;

      // Só agora a queda passa a ser inesperada: antes disto, um fechamento é
      // uma tentativa de conexão que falhou, e quem chamou já trata.
      this.vivo = true;
      transport.onclose = () => this.aoFechar('o processo do RAGX encerrou');
      transport.onerror = (e: Error) => this.aoFechar(e.message);

      this.timings = {
        spawnBootHandshakeMs,
        listToolsMs,
        handshakeMs,
        totalMs: Date.now() - t0,
      };
      // Uma linha por conexão, com a repartição. É o que transforma "o RAGX
      // está lento" em "o boot do Python leva 1,6 s" sem precisar de profiler.
      this.log(
        `MCP pronto em ${this.timings.totalMs}ms — ${this.tools.size} ferramentas ` +
          `(spawn+boot+handshake ${spawnBootHandshakeMs}ms · ` +
          `listTools ${listToolsMs}ms · playbook ${handshakeMs}ms)`,
      );

      return done({
        name: project,
        root: this.options.cwd,
        transport: 'mcp',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.log(`falha ao conectar após ${Date.now() - t0}ms: ${message}`);
      return fail('spawn_failed', message);
    }
  }

  /** Repartição da última conexão bem-sucedida. */
  medidas(): ConnectTimings | undefined {
    return this.timings;
  }

  private aoFechar(motivo: string): void {
    // `dispose()` zera `vivo` ANTES de fechar: desligar de propósito não é
    // queda, e avisar que caiu dispararia uma reconexão contra um cliente que
    // acabou de ser trocado.
    if (!this.vivo) return;
    this.vivo = false;
    this.client = undefined;
    this.log(`conexão perdida: ${motivo}`);
    this.options.onCrash?.(motivo);
  }

  async dispose(): Promise<void> {
    this.vivo = false;
    try {
      await this.client?.close();
    } catch {
      /* fechar um transporte já morto não é erro que interesse a ninguém */
    }
    this.child?.kill();
    this.client = undefined;
  }

  has(tool: string): boolean {
    return this.tools.has(tool);
  }

  /** Chamada bruta. Desempacota o envelope `{ok, data}` do RAGX. */
  private async call<T>(
    tool: string,
    args: Json,
    signal?: AbortSignal,
  ): Promise<RagResult<T>> {
    if (!this.client) return fail('disconnected', 'MCP não conectado');
    if (!this.tools.has(tool)) {
      return fail(
        'unsupported',
        `esta instalação do RAGX não expõe "${tool}" — atualize o RAGX`,
      );
    }
    try {
      const res = await this.client.callTool(
        { name: tool, arguments: args },
        undefined,
        { timeout: this.options.timeoutMs ?? DEFAULT_TIMEOUT, signal },
      );
      const content = (res.content ?? []) as Array<{ type: string; text?: string }>;
      const text = content.find((c) => c.type === 'text')?.text;
      if (!text) return fail('empty', `${tool} não devolveu conteúdo`);

      const parsed = JSON.parse(text) as { ok?: boolean; data?: T; error?: Json };
      if (parsed.ok === false) {
        const e = (parsed.error ?? {}) as { code?: string; message?: string };
        return fail(e.code ?? 'error', e.message ?? 'falha sem detalhe');
      }
      return done((parsed.data ?? parsed) as T);
    } catch (err) {
      if (signal?.aborted) return fail('aborted', 'consulta cancelada');
      const message = err instanceof Error ? err.message : String(err);
      const code = /timed? ?out/i.test(message) ? 'timeout' : 'transport';
      this.log(`${tool}: ${message}`);
      return fail(code, message);
    }
  }

  // ── leitura ───────────────────────────────────────────────────────────
  async stats(): Promise<RagResult<KnowledgeStats>> {
    const r = await this.call<Json>('task_status', {});
    const dict = await this.call<Json>('get_dictionary', { section: 'project' });

    // `task_status` traz o painel consolidado; se esta instalação for antiga e
    // não tiver a ferramenta, o dicionário ainda dá o essencial.
    const k = (r.ok ? (r.data?.knowledge as Json) : undefined) ?? {};
    const projeto = (dict.ok ? (dict.data?.dictionary as Json) : undefined) ?? {};
    const p = (projeto.project as Json) ?? {};

    return done({
      initialized: Object.keys(k).length > 0,
      documents: num(k.documents),
      chunks: num(k.chunks),
      embeddings: num(k.chunks),
      entities: num(k.entities),
      relations: num(k.relations),
      securityEvents: num(p.security_events),
      byLang: (p.by_lang as Record<string, number>) ?? {},
      lastRun: p.generated_at ? { mode: 'sync', finishedAt: String(p.generated_at) } : undefined,
    });
  }

  async health(): Promise<RagResult<HealthCheck[]>> {
    const checks: HealthCheck[] = [];
    const stats = await this.stats();
    checks.push({
      name: 'RAGX',
      status: this.client ? 'ok' : 'error',
      detail: this.client ? 'conectado por MCP' : 'sem conexão',
    });
    checks.push({
      name: 'Índice',
      status: stats.ok && (stats.data?.chunks ?? 0) > 0 ? 'ok' : 'warn',
      detail: stats.ok ? `${stats.data?.chunks ?? 0} chunks` : 'indisponível',
    });
    checks.push({
      name: 'Grafo',
      status: stats.ok && (stats.data?.entities ?? 0) > 0 ? 'ok' : 'warn',
      detail: stats.ok ? `${stats.data?.entities ?? 0} entidades` : 'indisponível',
    });
    const sec = await this.security();
    checks.push({
      name: 'Segurança',
      status: sec.ok && sec.data?.gateActive ? 'ok' : 'warn',
      detail: sec.ok ? `política ${sec.data?.policy}` : 'indisponível',
    });
    checks.push({
      name: 'MCP',
      status: this.tools.size > 0 ? 'ok' : 'error',
      detail: `${this.tools.size} ferramentas`,
    });
    return done(checks);
  }

  async search(
    query: string,
    mode: SearchMode,
    limit: number,
    filters?: SearchFilters,
    signal?: AbortSignal,
  ): Promise<RagResult<SearchResponse>> {
    const tool = mode === 'semantic' ? 'search_knowledge' : 'search_hybrid';
    const args: Json = { query, limit: Math.min(limit, MAX_SEARCH_LIMIT) };
    if (filters?.lang) args.lang = filters.lang;
    if (filters?.kind) args.kind = filters.kind;
    if (filters?.pathGlob) args.path_glob = filters.pathGlob;
    // O RAGX aceita `current`, `all` e `project:<nome>`. Mandar sempre deixa a
    // origem explícita no servidor em vez de implícita no cliente.
    if (filters?.scope) args.scope = filters.scope;

    const r = await this.call<Json>(tool, args, signal);
    if (!r.ok) return propagate<SearchResponse>(r);

    const raw = (r.data?.results as Json[]) ?? [];
    let results = raw.map(toHit);
    if (filters?.minScore) {
      results = results.filter((h) => h.score >= filters.minScore!);
    }
    return done({
      query,
      mode,
      degraded: (r.data?.degraded as string) ?? null,
      results,
    });
  }

  async graph(
    entity: string,
    depth: number,
    maxNodes: number,
  ): Promise<RagResult<GraphSlice>> {
    const r = await this.call<Json>('get_entity', { name: entity, depth });
    if (!r.ok) return propagate<GraphSlice>(r);

    const centro = (r.data?.entity as Json) ?? {};
    const relacoes = (r.data?.relations as Json[]) ?? [];

    const nodes = new Map<string, GraphNode>();
    const centroId = str(centro.id) || str(centro.name) || entity;
    nodes.set(centroId, {
      id: centroId,
      name: str(centro.name) || entity,
      type: str(centro.type) || 'entity',
      qualifiedName: str(centro.qualified_name) || null,
      documentPath: str(centro.document_path) || null,
      summary: str(centro.summary) || null,
      confidence: numOrUndef(centro.confidence),
      source: str(centro.source) || undefined,
      tier: tierOf(centro.tier),
      expanded: true,
    });

    const edges: GraphEdge[] = [];
    for (const rel of relacoes) {
      if (nodes.size >= maxNodes) break;
      const aresta = toEdge(rel, centroId);
      if (!aresta) continue;

      // O nó do outro lado. `other_id` é quem identifica; o nome é rótulo, e
      // dois símbolos homônimos em arquivos diferentes têm o MESMO nome.
      const outroId = aresta.source === centroId ? aresta.target : aresta.source;
      if (!nodes.has(outroId)) {
        // `rel` só carrega a confiança da ARESTA, não a da entidade vizinha.
        // Esse nó fica sem `confidence`/`tier` até ser expandido como centro
        // (uma futura chamada `get_entity` nele) — inventar um valor aqui
        // atribuiria à entidade uma confiança que na verdade é da relação.
        nodes.set(outroId, {
          id: outroId,
          name: str(rel.other) || str(rel.other_name) || outroId,
          type: str(rel.other_type) || 'entity',
          qualifiedName: str(rel.other_qualified_name) || null,
          expanded: false,
        });
      }
      edges.push(aresta);
    }

    return done({
      nodes: [...nodes.values()],
      edges,
      truncated: relacoes.length > 0 && nodes.size >= maxNodes,
    });
  }

  async entity(name: string): Promise<RagResult<EntityDetail>> {
    const r = await this.call<Json>('get_entity', { name, depth: 1 });
    if (!r.ok) return propagate<EntityDetail>(r);
    const e = (r.data?.entity as Json) ?? {};
    // `other` é o nó do outro lado — o campo que o servidor manda. Ler
    // `target`/`name` aqui mostrava "?" em toda relação, porque nenhum dos
    // dois existe na resposta. Os antigos ficam como reserva, e só.
    const relacoes = ((r.data?.relations as Json[]) ?? []).map((rel) => ({
      type: str(rel.type) || 'related',
      direction: (str(rel.direction) === 'in' ? 'in' : 'out') as 'in' | 'out',
      // `other` é o campo que o servidor manda. Ler `target`/`name` aqui
      // mostrava "?" em toda relação, porque nenhum dos dois existe na
      // resposta; os antigos ficam como reserva, e só.
      target: str(rel.other) || str(rel.other_name) || str(rel.target) || '?',
      targetId: str(rel.other_id) || str(rel.target_id) || undefined,
      confidence: numOrUndef(rel.confidence),
      source: str(rel.source) || undefined,
      tier: tierOf(rel.tier),
    }));
    const fontes: Array<{ path: string; line?: number }> = [];
    const doc = str(e.document_path);
    if (doc) fontes.push({ path: doc, line: num(e.line) || undefined });
    for (const s of (r.data?.sources as Json[]) ?? []) {
      const p = str(s.path) || str(s.document_path);
      if (p) fontes.push({ path: p, line: num(s.line) || undefined });
    }
    return done({
      entity: {
        id: str(e.id) || name,
        name: str(e.name) || name,
        type: str(e.type) || 'entity',
        qualifiedName: str(e.qualified_name) || null,
        documentPath: doc || null,
        summary: str(e.summary) || null,
        confidence: numOrUndef(e.confidence),
        source: str(e.source) || undefined,
        tier: tierOf(e.tier),
      },
      relations: relacoes,
      sources: fontes,
    });
  }

  async dictionary(): Promise<RagResult<DictionarySection[]>> {
    const r = await this.call<Json>('get_dictionary', {});
    if (!r.ok) return propagate<DictionarySection[]>(r);
    const d = (r.data?.dictionary as Json) ?? {};

    const rotulos: Record<string, string> = {
      project: 'Projeto',
      technologies: 'Tecnologias',
      services: 'Serviços',
      entrypoints: 'Pontos de entrada',
      data_stores: 'Armazenamento',
      modules: 'Módulos',
      concepts: 'Conceitos de negócio',
      conventions: 'Convenções',
      glossary: 'Glossário',
      docs: 'Documentação',
    };

    const secoes: DictionarySection[] = [];
    for (const [id, valor] of Object.entries(d)) {
      if (id === 'schema_version') continue;
      const items = toItems(valor);
      if (!items.length) continue;
      secoes.push({ id, label: rotulos[id] ?? id, items });
    }
    return done(secoes);
  }

  async documents(query?: string, limit = 200): Promise<RagResult<DocumentInfo[]>> {
    // O inventário é a resposta certa: diz o que EXISTE no índice, não o que
    // casa com uma consulta. A derivação por busca abaixo continua como
    // reserva para instalações do RAGX anteriores a esta ferramenta.
    if (this.tools.has('list_documents')) {
      const inventario = await this.call<Json>('list_documents', {
        path_glob: query || undefined,
        limit: Math.min(limit, 2000),
      });
      if (inventario.ok) {
        return done(((inventario.data?.documents as Json[]) ?? []).map(toDocument));
      }
    }

    const r = await this.search(query || '.', 'keyword', limit);
    if (!r.ok) return propagate<DocumentInfo[]>(r);

    const porCaminho = new Map<string, DocumentInfo>();
    for (const hit of r.data?.results ?? []) {
      const atual = porCaminho.get(hit.documentPath);
      if (atual) {
        atual.chunks += 1;
        continue;
      }
      porCaminho.set(hit.documentPath, {
        path: hit.documentPath,
        lang: null,
        kind: hit.kind,
        title: hit.headingPath?.split(' > ')[0] ?? null,
        chunks: 1,
        redacted: false,
      });
    }
    return done([...porCaminho.values()].sort((a, b) => a.path.localeCompare(b.path)));
  }

  async fileKnowledge(relPath: string): Promise<RagResult<FileKnowledge>> {
    const r = await this.call<Json>('get_document', { path: relPath });
    if (!r.ok) {
      return done({
        path: relPath,
        indexed: false,
        reason:
          r.error?.code === 'not_found'
            ? 'não indexado — pode ter sido bloqueado pelo Security Gate'
            : r.error?.message,
        chunks: [],
        entities: [],
      });
    }
    const doc = (r.data?.document as Json) ?? {};
    const chunks: ChunkInfo[] = ((r.data?.chunks as Json[]) ?? []).map((c) => ({
      chunkId: str(c.chunk_id),
      ordinal: num(c.ordinal),
      kind: str(c.kind),
      symbol: str(c.symbol) || null,
      headingPath: str(c.heading_path) || null,
      lines: pair(c.lines),
      tokens: num(c.tokens),
    }));
    const simbolos = [...new Set(chunks.map((c) => c.symbol).filter(Boolean))] as string[];
    return done({
      path: relPath,
      indexed: true,
      chunks,
      entities: simbolos.slice(0, 12),
      document: {
        path: str(doc.path) || relPath,
        lang: str(doc.lang) || null,
        kind: str(doc.kind) || null,
        title: str(doc.title) || null,
        chunks: chunks.length,
        redacted: Boolean(doc.redacted),
      },
    });
  }

  async sources(): Promise<RagResult<SourcesOverview>> {
    const [base, projetos, stats] = await Promise.all([
      this.call<Json>('list_base_sources', {}),
      this.call<Json>('list_projects', {}),
      this.stats(),
    ]);
    // Nenhuma das três é obrigatória: sem hub não há projetos, sem fonte base
    // não há `@base/`, e o projeto atual continua sendo uma origem válida.
    return done(
      toSources(
        base.ok ? base.data ?? {} : {},
        projetos.ok ? projetos.data ?? {} : {},
        {
          name: this.projeto,
          documents: stats.ok ? stats.data?.documents : undefined,
          chunks: stats.ok ? stats.data?.chunks : undefined,
          entities: stats.ok ? stats.data?.entities : undefined,
        },
      ),
    );
  }

  async chunk(chunkId: string): Promise<RagResult<ChunkInfo>> {
    const r = await this.call<Json>('get_chunk', { chunk_id: chunkId });
    if (!r.ok) return propagate<ChunkInfo>(r);
    const c = (r.data?.chunk as Json) ?? r.data ?? {};
    return done(toChunk(c, chunkId));
  }

  // ── orquestração ──────────────────────────────────────────────────────
  async tasks(project?: string, status?: string): Promise<RagResult<TaskInfo[]>> {
    const args: Json = { limit: 200 };
    if (project) args.project_id = project;
    if (status) args.status = status;
    const r = await this.call<Json>('list_tasks', args);
    if (!r.ok) return propagate<TaskInfo[]>(r);
    return done(((r.data?.tasks as Json[]) ?? []).map(toTask));
  }

  async task(taskId: string): Promise<RagResult<TaskDetail>> {
    const r = await this.call<Json>('get_task', { task_id: taskId });
    if (!r.ok) return propagate<TaskDetail>(r);
    return done(toTaskDetail(r.data ?? {}, taskId));
  }

  async taskGraph(project?: string): Promise<RagResult<TaskGraph>> {
    const r = await this.call<Json>('task_graph', project ? { project_id: project } : {});
    if (!r.ok) return propagate<TaskGraph>(r);
    return done(toTaskGraph(r.data ?? {}));
  }

  async taskPanel(): Promise<RagResult<TaskPanel>> {
    const r = await this.call<Json>('task_status', {});
    // Projeto sem banco de orquestração é o caso COMUM, não uma falha: quem
    // nunca rodou `ragx task plan` não tem tarefa nenhuma. Devolver erro aqui
    // pintaria a tela de vermelho por uma situação normal.
    if (!r.ok) {
      return done({
        counts: {},
        projects: [],
        unavailable: r.error?.message ?? 'orquestração indisponível',
      });
    }
    return done(toTaskPanel(r.data ?? {}));
  }

  async analyzeRequest(request: string): Promise<RagResult<RequestAnalysis>> {
    const r = await this.call<Json>('analyze_request', { request });
    if (!r.ok) return propagate<RequestAnalysis>(r);
    return done(toAnalysis(r.data ?? {}));
  }

  async buildContext(query: string, tokens: number): Promise<RagResult<ContextPack>> {
    const r = await this.call<Json>('build_context', {
      query,
      tokens,
      format: 'markdown',
    });
    if (!r.ok) return propagate<ContextPack>(r);
    const frags = ((r.data?.fragments as Json[]) ?? []).map((f) => ({
      chunkId: str(f.chunk_id),
      documentPath: str(f.document_path),
      lines: pair(f.lines),
      tokens: num(f.tokens),
      content: str(f.content),
      symbol: str(f.symbol) || null,
    }));
    return done({
      query,
      estimatedTokens: num(r.data?.estimated_tokens),
      budget: num(r.data?.budget) || tokens,
      fragments: frags,
      sources: (r.data?.sources as string[]) ?? frags.map((f) => f.documentPath),
      markdown: str(r.data?.markdown) || undefined,
    });
  }

  async security(): Promise<RagResult<SecurityStatus>> {
    // Não existe ferramenta MCP de segurança, e isso é proposital: o servidor
    // não serve a lista de arquivos bloqueados, que é um mapa de onde estão os
    // segredos. O que dá para afirmar com certeza vem do próprio índice.
    const stats = await this.stats();
    return done({
      gateActive: true,
      policy: 'strict',
      rules: 0,
      blockedFiles: stats.ok ? stats.data?.securityEvents ?? 0 : 0,
      redactedFiles: 0,
      reasons: [],
      ignoreFiles: ['.gitignore', '.dockerignore', '.ragignore'],
      indexedSecrets: 0,
      embeddedSecrets: 0,
    });
  }

  async monitor(): Promise<RagResult<MonitorSnapshot>> {
    const stats = await this.stats();
    const painel = await this.call<Json>('task_status', {});
    return done({
      stats: stats.ok ? stats.data! : emptyStats(),
      activity: [],
      tasks: painel.ok ? ((painel.data?.tasks as Record<string, number>) ?? {}) : {},
      scheduler: painel.ok
        ? (painel.data?.scheduler as MonitorSnapshot['scheduler'])
        : undefined,
    });
  }

  async agents(): Promise<RagResult<AgentInfo[]>> {
    // Perfis de agente são artefatos em disco (`agents/<nome>/`), fora do MCP.
    // O cliente CLI responde isto; aqui devolvemos vazio em vez de inventar.
    return done([]);
  }

  async sync(): Promise<RagResult<{ indexed: number; removed: number; warnings: string[] }>> {
    const r = await this.call<Json>('refresh', {});
    if (!r.ok) return propagate<{ indexed: number; removed: number; warnings: string[] }>(r);
    return done({
      indexed: num(r.data?.indexed),
      removed: 0,
      warnings: (r.data?.warnings as string[]) ?? [],
    });
  }
}

// ── conversões ──────────────────────────────────────────────────────────
function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

/** Número ausente é AUSENTE, não zero: `confidence: 0` significa outra coisa. */
function numOrUndef(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

function pair(v: unknown): [number, number] {
  if (Array.isArray(v) && v.length >= 2) return [num(v[0]), num(v[1])];
  return [0, 0];
}


function toHit(r: Record<string, unknown>): SearchHit {
  return {
    chunkId: str(r.chunk_id),
    project: str(r.project) || 'current',
    documentPath: str(r.document_path),
    symbol: str(r.symbol) || null,
    headingPath: str(r.heading_path) || null,
    kind: str(r.kind) || 'block',
    lines: pair(r.lines),
    score: num(r.score),
    content: str(r.content),
    matchedBy: (r.matched_by as string[]) ?? [],
  };
}

function toItems(valor: unknown): DictionaryItem[] {
  if (Array.isArray(valor)) {
    return valor.map((v) =>
      typeof v === 'string'
        ? { name: v }
        : {
            name: str((v as Json).name) || JSON.stringify(v).slice(0, 60),
            description: str((v as Json).description) || undefined,
            evidence: ((v as Json).evidence as string[]) ?? undefined,
          },
    );
  }
  if (valor && typeof valor === 'object') {
    return Object.entries(valor as Json).map(([k, v]) => ({
      name: k,
      description: Array.isArray(v) ? undefined : String(v).slice(0, 200),
      related: Array.isArray(v) ? (v as string[]).map(String) : undefined,
    }));
  }
  return [];
}

function emptyStats(): KnowledgeStats {
  return {
    initialized: false,
    documents: 0,
    chunks: 0,
    embeddings: 0,
    entities: 0,
    relations: 0,
    securityEvents: 0,
    byLang: {},
  };
}

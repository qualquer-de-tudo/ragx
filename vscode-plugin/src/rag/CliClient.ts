/**
 * Transporte CLI — reserva, e a única forma de ver o que o MCP não expõe.
 *
 * Mais lento (um processo por consulta, e a primeira busca carrega o modelo de
 * embeddings), mas sem estado e sem servidor. Duas coisas só existem aqui:
 *
 *   - `ragx security scan --json`, que o MCP deliberadamente não serve
 *   - `ragx agent list --json`, que lê perfis do disco
 *
 * Todo comando do RAGX aceita `--json`; nenhuma saída humana é interpretada.
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { done, fail, propagate, type RagClient } from './RagClient';
import type {
  AgentInfo,
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
  SearchFilters,
  SearchMode,
  SearchResponse,
  SecurityStatus,
} from './types';

const run = promisify(execFile);

export interface CliOptions {
  command: string;
  cwd: string;
  timeoutMs?: number;
  log?: (line: string) => void;
}

type Json = Record<string, unknown>;

export class CliRagClient implements RagClient {
  readonly transport = 'cli' as const;

  constructor(private options: CliOptions) {}

  private log(line: string): void {
    this.options.log?.(line);
  }

  /** Executa e devolve JSON. Nunca lança por falha do RAGX. */
  async exec<T>(args: string[]): Promise<RagResult<T>> {
    const inicio = Date.now();
    try {
      const { stdout } = await run(this.options.command, args, {
        cwd: this.options.cwd,
        timeout: this.options.timeoutMs ?? 180_000,
        // Saída de projeto grande passa de 1 MB com folga.
        maxBuffer: 64 * 1024 * 1024,
        windowsHide: true,
        encoding: 'utf8',
      });
      this.log(`ragx ${args.join(' ')} — ${Date.now() - inicio}ms`);
      const bruto = stdout.trim();
      if (!bruto) return done({} as T);
      return done(JSON.parse(stripNoise(bruto)) as T);
    } catch (err) {
      const e = err as NodeJS.ErrnoException & { stderr?: string; killed?: boolean };
      if (e.code === 'ENOENT') {
        return fail(
          'spawn_failed',
          `comando "${this.options.command}" não encontrado`,
        );
      }
      if (e.killed) return fail('timeout', 'o RAGX não respondeu a tempo');
      const detalhe = (e.stderr || e.message || '').trim();
      this.log(`ragx ${args.join(' ')} FALHOU: ${detalhe.slice(0, 400)}`);
      return fail('cli', detalhe.split('\n')[0] || 'falha ao executar o RAGX');
    }
  }

  async connect(): Promise<RagResult<ProjectInfo>> {
    const r = await this.exec<Json>(['status', '--json']);
    if (!r.ok) return propagate<ProjectInfo>(r);
    if (!r.data?.initialized) {
      return fail('no_project', 'nenhum índice neste workspace — rode `ragx index .`');
    }
    return done({
      name: 'projeto',
      root: this.options.cwd,
      transport: 'cli',
    });
  }

  async dispose(): Promise<void> {
    /* sem processo persistente para encerrar */
  }

  async stats(): Promise<RagResult<KnowledgeStats>> {
    const r = await this.exec<Json>(['status', '--json']);
    if (!r.ok) return propagate<KnowledgeStats>(r);
    const d = r.data ?? {};
    const modelo = d.embedding_model as Json | undefined;
    const ultimo = d.last_run as Json | undefined;

    const grafo = await this.exec<Json>(['entities', '--limit', '1', '--json']);
    return done({
      initialized: Boolean(d.initialized),
      documents: num(d.documents),
      chunks: num(d.chunks),
      embeddings: num(d.embeddings),
      entities: grafo.ok ? num((grafo.data as Json)?.total) : 0,
      relations: grafo.ok ? num((grafo.data as Json)?.relations) : 0,
      securityEvents: num(d.security_events),
      byLang: (d.by_lang as Record<string, number>) ?? {},
      embeddingModel: modelo
        ? {
            id: String(modelo.id),
            dim: num(modelo.dim),
            versionedDim: num(modelo.versioned_dim),
          }
        : undefined,
      lastRun: ultimo
        ? {
            mode: String(ultimo.mode ?? 'index'),
            startedAt: ultimo.started_at as string,
            finishedAt: ultimo.finished_at as string,
            filesSeen: num(ultimo.files_seen),
            indexed: num(ultimo.indexed),
            blocked: num(ultimo.blocked),
            durationMs: num(ultimo.duration_ms),
          }
        : undefined,
    });
  }

  async health(): Promise<RagResult<HealthCheck[]>> {
    const r = await this.exec<Json>(['doctor', '--json']);
    if (!r.ok) {
      return done([{ name: 'RAGX', status: 'error', detail: r.error?.message }]);
    }
    const checks = (r.data?.checks as Json[]) ?? [];
    return done(
      checks.map((c) => ({
        name: String(c.name ?? '?'),
        status: (c.ok === true ? 'ok' : c.ok === false ? 'error' : 'warn') as
          | 'ok'
          | 'warn'
          | 'error',
        detail: c.detail ? String(c.detail) : undefined,
      })),
    );
  }

  async search(
    query: string,
    mode: SearchMode,
    limit: number,
    filters?: SearchFilters,
  ): Promise<RagResult<SearchResponse>> {
    const args = ['search', query, '--mode', mode, '--limit', String(limit), '--json'];
    if (filters?.lang) args.push('--lang', filters.lang);
    if (filters?.kind) args.push('--kind', filters.kind);

    const r = await this.exec<Json>(args);
    if (!r.ok) return propagate<SearchResponse>(r);
    let results = ((r.data?.results as Json[]) ?? []).map(toHit);
    if (filters?.minScore) results = results.filter((h) => h.score >= filters.minScore!);
    return done({
      query,
      mode,
      degraded: (r.data?.degraded as string) ?? null,
      timingsMs: (r.data?.timings_ms as Record<string, number>) ?? undefined,
      results,
    });
  }

  async graph(entity: string, depth: number, maxNodes: number): Promise<RagResult<GraphSlice>> {
    const r = await this.exec<Json>([
      'graph', 'show', entity, '--depth', String(depth), '--json',
    ]);
    if (!r.ok) return propagate<GraphSlice>(r);
    const nós = ((r.data?.nodes as Json[]) ?? []).slice(0, maxNodes).map((n) => ({
      id: String(n.id ?? n.name),
      name: String(n.name ?? n.id),
      type: String(n.type ?? 'entity'),
      documentPath: (n.document_path as string) ?? null,
      summary: (n.summary as string) ?? null,
    }));
    const ids = new Set(nós.map((n) => n.id));
    const arestas = ((r.data?.edges as Json[]) ?? [])
      .map((e) => ({
        source: String(e.src ?? e.source),
        target: String(e.dst ?? e.target),
        type: String(e.type ?? 'related'),
      }))
      .filter((e) => ids.has(e.source) && ids.has(e.target));
    return done({
      nodes: nós,
      edges: arestas,
      truncated: ((r.data?.nodes as Json[]) ?? []).length > maxNodes,
    });
  }

  async entity(name: string): Promise<RagResult<EntityDetail>> {
    const r = await this.exec<Json>(['graph', 'show', name, '--depth', '1', '--json']);
    if (!r.ok) return propagate<EntityDetail>(r);
    const nós = (r.data?.nodes as Json[]) ?? [];
    const centro = nós.find((n) => String(n.name) === name) ?? nós[0] ?? {};
    const centroId = String(centro.id ?? name);
    const relacoes = ((r.data?.edges as Json[]) ?? []).map((e) => {
      const saida = String(e.src ?? e.source) === centroId;
      const outroId = saida ? String(e.dst ?? e.target) : String(e.src ?? e.source);
      const outro = nós.find((n) => String(n.id) === outroId);
      return {
        type: String(e.type ?? 'related'),
        direction: (saida ? 'out' : 'in') as 'out' | 'in',
        target: String(outro?.name ?? outroId),
        targetId: outroId,
      };
    });
    const doc = (centro.document_path as string) ?? null;
    return done({
      entity: {
        id: centroId,
        name: String(centro.name ?? name),
        type: String(centro.type ?? 'entity'),
        documentPath: doc,
        summary: (centro.summary as string) ?? null,
      },
      relations: relacoes,
      sources: doc ? [{ path: doc }] : [],
    });
  }

  async dictionary(): Promise<RagResult<DictionarySection[]>> {
    const r = await this.exec<Json>(['dictionary', 'show', '--json']);
    if (!r.ok) return propagate<DictionarySection[]>(r);
    const rotulos: Record<string, string> = {
      project: 'Projeto', technologies: 'Tecnologias', services: 'Serviços',
      entrypoints: 'Pontos de entrada', data_stores: 'Armazenamento',
      modules: 'Módulos', concepts: 'Conceitos de negócio',
      conventions: 'Convenções', glossary: 'Glossário', docs: 'Documentação',
    };
    const secoes: DictionarySection[] = [];
    for (const [id, valor] of Object.entries(r.data ?? {})) {
      if (id === 'schema_version') continue;
      const items = toItems(valor);
      if (items.length) secoes.push({ id, label: rotulos[id] ?? id, items });
    }
    return done(secoes);
  }

  async documents(query?: string, limit = 200): Promise<RagResult<DocumentInfo[]>> {
    const args = ['documents', '--limit', String(limit), '--json'];
    if (query) args.push('--filter', query);
    const r = await this.exec<Json | Json[]>(args);
    if (!r.ok) return propagate<DocumentInfo[]>(r);
    const linhas = Array.isArray(r.data)
      ? (r.data as Json[])
      : ((r.data as Json)?.documents as Json[]) ?? [];
    return done(
      linhas.map((d) => ({
        path: String(d.rel_path ?? d.path ?? ''),
        lang: (d.lang as string) ?? null,
        kind: (d.doc_kind as string) ?? (d.kind as string) ?? null,
        title: (d.title as string) ?? null,
        chunks: num(d.chunks),
        redacted: Boolean(d.redacted),
      })),
    );
  }

  async fileKnowledge(relPath: string): Promise<RagResult<FileKnowledge>> {
    const r = await this.exec<Json | Json[]>(['chunks', relPath, '--json']);
    if (!r.ok) {
      return done({
        path: relPath,
        indexed: false,
        reason: 'não indexado — pode ter sido bloqueado pelo Security Gate',
        chunks: [],
        entities: [],
      });
    }
    const linhas = Array.isArray(r.data)
      ? (r.data as Json[])
      : ((r.data as Json)?.chunks as Json[]) ?? [];
    const chunks = linhas.map((c) => ({
      chunkId: String(c.id ?? c.chunk_id ?? ''),
      ordinal: num(c.ordinal),
      kind: String(c.kind ?? 'block'),
      symbol: (c.symbol as string) ?? null,
      headingPath: (c.heading_path as string) ?? null,
      lines: [num(c.start_line), num(c.end_line)] as [number, number],
      tokens: num(c.token_count ?? c.tokens),
    }));
    return done({
      path: relPath,
      indexed: chunks.length > 0,
      chunks,
      entities: [...new Set(chunks.map((c) => c.symbol).filter(Boolean))] as string[],
    });
  }

  async buildContext(query: string, tokens: number): Promise<RagResult<ContextPack>> {
    const r = await this.exec<Json>([
      'context', query, '--tokens', String(tokens), '--json',
    ]);
    if (!r.ok) return propagate<ContextPack>(r);
    const frags = ((r.data?.fragments as Json[]) ?? []).map((f) => ({
      chunkId: String(f.chunk_id ?? ''),
      documentPath: String(f.document_path ?? ''),
      lines: [num((f.lines as number[])?.[0]), num((f.lines as number[])?.[1])] as [number, number],
      tokens: num(f.tokens),
      content: String(f.content ?? ''),
      symbol: (f.symbol as string) ?? null,
    }));
    return done({
      query,
      estimatedTokens: num(r.data?.estimated_tokens),
      budget: num(r.data?.budget) || tokens,
      fragments: frags,
      sources: (r.data?.sources as string[]) ?? [],
      markdown: (r.data?.markdown as string) ?? undefined,
    });
  }

  async security(): Promise<RagResult<SecurityStatus>> {
    const r = await this.exec<Json>(['security', 'scan', '.', '--json']);
    if (!r.ok) return propagate<SecurityStatus>(r);
    const d = r.data ?? {};

    // Agrega por REGRA, nunca por arquivo. A lista de caminhos bloqueados é um
    // mapa de onde estão os segredos — §19 do pedido é explícito sobre isso, e
    // a agregação acontece aqui, antes de qualquer coisa chegar à webview.
    const porRegra = new Map<string, number>();
    for (const item of (d.blocked as Json[]) ?? []) {
      const regra = String(item.rule_id ?? item.reason ?? 'desconhecida');
      porRegra.set(regra, (porRegra.get(regra) ?? 0) + 1);
    }

    return done({
      gateActive: true,
      policy: String(d.policy ?? 'strict'),
      rules: num(d.rules),
      blockedFiles: num(d.blocked_count) || ((d.blocked as Json[]) ?? []).length,
      redactedFiles: num(d.redacted_count) || ((d.redacted as Json[]) ?? []).length,
      reasons: [...porRegra.entries()]
        .map(([rule, count]) => ({ rule, count }))
        .sort((a, b) => b.count - a.count),
      ignoreFiles: (d.ignore_files as string[]) ?? [
        '.gitignore', '.dockerignore', '.ragignore',
      ],
      indexedSecrets: 0,
      embeddedSecrets: 0,
    });
  }

  async monitor(): Promise<RagResult<MonitorSnapshot>> {
    const stats = await this.stats();
    if (!stats.ok) return propagate<MonitorSnapshot>(stats);
    const ultimo = stats.data?.lastRun;
    return done({
      stats: stats.data!,
      activity: ultimo
        ? [
            {
              at: ultimo.finishedAt ?? '',
              kind: ultimo.mode,
              message:
                `${ultimo.indexed ?? 0} documento(s) indexado(s)` +
                (ultimo.blocked ? `, ${ultimo.blocked} bloqueado(s)` : ''),
            },
          ]
        : [],
    });
  }

  async agents(): Promise<RagResult<AgentInfo[]>> {
    const r = await this.exec<Json | Json[]>(['agent', 'list', '--json']);
    if (!r.ok) return done([]);
    const linhas = Array.isArray(r.data)
      ? (r.data as Json[])
      : ((r.data as Json)?.agents as Json[]) ?? [];
    return done(
      linhas.map((a) => ({
        name: String(a.name ?? '?'),
        state: (String(a.state ?? 'ready') as AgentInfo['state']) ?? 'unknown',
        chunks: num(a.chunks),
        skills: num(a.skills),
        rules: num(a.rules),
        examples: num(a.examples),
        coverage: typeof a.coverage === 'number' ? a.coverage : undefined,
        sources: (a.sources as string[]) ?? undefined,
      })),
    );
  }

  async sync(): Promise<RagResult<{ indexed: number; removed: number; warnings: string[] }>> {
    // `watch --once` é o sync INCREMENTAL. Nunca `index --full`: reindexar o
    // repositório a cada save é o erro que a §48 manda evitar.
    const r = await this.exec<Json>(['watch', '--once', '--plain']);
    if (!r.ok) return propagate<{ indexed: number; removed: number; warnings: string[] }>(r);
    return done({
      indexed: num(r.data?.indexed),
      removed: 0,
      warnings: (r.data?.warnings as string[]) ?? [],
    });
  }
}

// ── auxiliares ──────────────────────────────────────────────────────────
function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

/**
 * O RAGX às vezes escreve aviso de biblioteca antes do JSON (carga de modelo,
 * por exemplo). Corta tudo até a primeira chave ou colchete.
 */
function stripNoise(texto: string): string {
  const i = texto.search(/[[{]/);
  return i > 0 ? texto.slice(i) : texto;
}

function toHit(r: Json) {
  return {
    chunkId: String(r.chunk_id ?? ''),
    project: String(r.project ?? 'current'),
    documentPath: String(r.document_path ?? ''),
    symbol: (r.symbol as string) ?? null,
    headingPath: (r.heading_path as string) ?? null,
    kind: String(r.kind ?? 'block'),
    lines: [num((r.lines as number[])?.[0]), num((r.lines as number[])?.[1])] as [number, number],
    score: num(r.score),
    content: String(r.content ?? ''),
    matchedBy: (r.matched_by as string[]) ?? [],
  };
}

function toItems(valor: unknown) {
  if (Array.isArray(valor)) {
    return valor.map((v) =>
      typeof v === 'string'
        ? { name: v }
        : {
            name: String((v as Json).name ?? '?'),
            description: (v as Json).description
              ? String((v as Json).description)
              : undefined,
            evidence: ((v as Json).evidence as string[]) ?? undefined,
          },
    );
  }
  if (valor && typeof valor === 'object') {
    return Object.entries(valor as Json).map(([k, v]) => ({
      name: k,
      related: Array.isArray(v) ? (v as unknown[]).map(String) : undefined,
      description: Array.isArray(v) ? undefined : String(v).slice(0, 200),
    }));
  }
  return [];
}

/**
 * Conversões do JSON do RAGX para os tipos do plugin.
 *
 * Ficam aqui, e não em cada transporte, porque MCP e CLI devolvem a MESMA
 * estrutura para tarefa, chunk e análise — só o meio muda. Duplicar a
 * conversão nos dois lados produziria o bug que só aparece no transporte que
 * ninguém testou: campo renomeado no servidor, uma tela certa e outra vazia.
 *
 * Toda função aqui é total: entrada malformada vira valor neutro, nunca
 * exceção. Um campo a menos no servidor não pode apagar a tela.
 */

import type {
  ChunkInfo,
  DocumentInfo,
  GraphEdge,
  KnowledgeSource,
  RequestAnalysis,
  SourcesOverview,
  TaskDetail,
  TaskGraph,
  TaskInfo,
  TaskPanel,
} from './types';

type Json = Record<string, unknown>;

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

function bool(v: unknown): boolean {
  return v === true || v === 1 || v === 'true';
}

function lista(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => (typeof x === 'string' ? x : String(x))).filter(Boolean);
}

function pair(v: unknown): [number, number] {
  if (Array.isArray(v) && v.length >= 2) return [num(v[0]), num(v[1])];
  return [0, 0];
}

function obj(v: unknown): Json {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Json) : {};
}

/**
 * Um chunk vindo do MCP ou da CLI.
 *
 * As duas origens nomeiam os mesmos campos de forma diferente: o MCP devolve
 * `lines: [a, b]` e `tokens`; a linha do banco, que a CLI imprime, traz
 * `start_line`, `end_line` e `token_count`. Aceitar os dois aqui evita uma
 * segunda conversão — e o painel de detalhe vazio no transporte de reserva.
 */
export function toChunk(c: Json, fallbackId = ''): ChunkInfo {
  const linhas = Array.isArray(c.lines)
    ? pair(c.lines)
    : ([num(c.start_line), num(c.end_line)] as [number, number]);
  return {
    chunkId: str(c.chunk_id) || str(c.id) || fallbackId,
    ordinal: num(c.ordinal),
    kind: str(c.kind) || 'block',
    symbol: str(c.symbol) || null,
    headingPath: str(c.heading_path) || null,
    lines: linhas,
    tokens: num(c.tokens) || num(c.token_count),
    content: str(c.content) || undefined,
    documentPath: str(c.document_path) || str(c.rel_path) || undefined,
  };
}

export function toDocument(d: Json): DocumentInfo {
  return {
    path: str(d.path) || str(d.rel_path),
    lang: str(d.lang) || null,
    kind: str(d.kind) || str(d.doc_kind) || null,
    title: str(d.title) || null,
    chunks: num(d.chunks),
    redacted: d.redacted === true || d.redacted === 1,
  };
}

export function toTask(t: Json): TaskInfo {
  return {
    id: str(t.id),
    projectId: str(t.project_id),
    title: str(t.title) || str(t.id) || 'sem título',
    status: str(t.status) || 'pending',
    priority: str(t.priority) || 'normal',
    track: str(t.track),
    type: str(t.type),
    requiresApproval: bool(t.requires_approval),
    acceptanceCriteria: lista(t.acceptance_criteria),
    filesScope: lista(t.files_scope),
    retryCount: num(t.retry_count),
  };
}

/** Referência a outra tarefa. O servidor manda id puro ou objeto — aceita os dois. */
function toRef(v: unknown): { id: string; title?: string; status?: string } {
  if (typeof v === 'string') return { id: v };
  const o = obj(v);
  return {
    id: str(o.id) || str(o.task_id) || str(o.depends_on),
    title: str(o.title) || undefined,
    status: str(o.status) || undefined,
  };
}

export function toTaskDetail(d: Json, fallbackId = ''): TaskDetail {
  const t = obj(d.task);
  const base = toTask(t);
  const resultado = obj(d.last_result ?? d.result);
  const payload = Object.keys(obj(resultado.payload)).length
    ? obj(resultado.payload)
    : resultado;

  return {
    task: {
      ...base,
      id: base.id || fallbackId,
      description: str(t.description) || undefined,
      testRequirements: lista(t.test_requirements),
      securityRequirements: lista(t.security_requirements),
      createdAt: str(t.created_at) || undefined,
      updatedAt: str(t.updated_at) || undefined,
      leaseExpiresAt: str(t.lease_expires_at) || undefined,
      assignee: str(t.assignee) || str(t.agent_id) || undefined,
    },
    dependencies: (Array.isArray(d.dependencies) ? d.dependencies : []).map(toRef),
    dependents: (Array.isArray(d.dependents) ? d.dependents : []).map(toRef),
    lastResult: Object.keys(payload).length
      ? {
          status: str(payload.status) || undefined,
          summary: str(payload.summary) || undefined,
          filesChanged: lista(payload.files_changed),
          checks: (Array.isArray(payload.checks) ? payload.checks : []).map((c) => {
            const o = obj(c);
            return {
              name: str(o.name) || 'check',
              passed: bool(o.passed ?? o.ok),
              detail: str(o.detail) || str(o.message) || undefined,
            };
          }),
        }
      : undefined,
  };
}

export function toTaskGraph(d: Json): TaskGraph {
  const nodes = (Array.isArray(d.nodes) ? d.nodes : []).map((n) => {
    const o = obj(n);
    return {
      id: str(o.id),
      title: str(o.title) || str(o.id),
      status: str(o.status) || 'pending',
      track: str(o.track) || undefined,
    };
  });
  const ids = new Set(nodes.map((n) => n.id));
  const edges = (Array.isArray(d.edges) ? d.edges : [])
    .map((e) => {
      const o = obj(e);
      return {
        from: str(o.from) || str(o.source) || str(o.task_id),
        to: str(o.to) || str(o.target) || str(o.depends_on),
        kind: str(o.kind) || 'depends_on',
      };
    })
    // Aresta para um nó que não veio (a listagem tem teto) desenharia uma
    // seta para o nada. Descartar é mais honesto que inventar o nó.
    .filter((e) => ids.has(e.from) && ids.has(e.to));
  return { nodes, edges };
}

export function toTaskPanel(d: Json): TaskPanel {
  const contagens: Record<string, number> = {};
  for (const [k, v] of Object.entries(obj(d.tasks))) {
    if (typeof v === 'number') contagens[k] = v;
  }
  const agenda = obj(d.scheduler);
  return {
    counts: contagens,
    projects: (Array.isArray(d.projects) ? d.projects : []).map((p) => {
      const o = obj(p);
      return {
        id: str(o.id),
        name: str(o.name) || str(o.id),
        status: str(o.status) || 'active',
      };
    }),
    scheduler: Object.keys(agenda).length
      ? {
          total: num(agenda.total),
          enabled: num(agenda.enabled),
          next: typeof agenda.next === 'string' ? agenda.next : null,
        }
      : undefined,
    // O painel do RAGX devolve o erro do banco de orquestração DENTRO da
    // resposta, em vez de falhar — é a mesma escolha feita aqui.
    unavailable: str(d.tasks_error) || undefined,
  };
}

/**
 * Monta a lista de origens a partir das três respostas que o RAGX dá.
 *
 * `base` e `projects` vêm de ferramentas diferentes e nenhuma delas conhece a
 * outra: quem junta é o plugin. O projeto atual entra SEMPRE, mesmo sem hub e
 * sem fonte base — uma tela de origens que aparece vazia no caso mais comum
 * seria pior que não existir.
 */
export function toSources(
  base: Json,
  projetos: Json,
  atual: { name: string; documents?: number; chunks?: number; entities?: number },
  declaradas: string[] = [],
): SourcesOverview {
  const declaradasSet = new Set(
    declaradas.length ? declaradas : lista(base.required_by_project),
  );
  const prefixo = str(base.prefix) || '@base/';

  const fontes: KnowledgeSource[] = [
    {
      id: 'project',
      kind: 'project',
      name: atual.name || 'este projeto',
      enabled: true,
      documents: atual.documents,
      chunks: atual.chunks,
      entities: atual.entities,
      scope: 'current',
    },
  ];

  for (const s of (Array.isArray(base.sources) ? base.sources : []) as unknown[]) {
    const o = obj(s);
    const nome = str(o.name);
    if (!nome) continue;
    fontes.push({
      id: `${prefixo}${nome}`,
      kind: 'base',
      name: nome,
      origin: str(o.origin) || undefined,
      commit: str(o.commit) || undefined,
      enabled: o.enabled !== false,
      // Instalada não é o mesmo que em uso: o índice deste projeto só recebe
      // as fontes que ele DECLARA. A UI precisa separar as duas coisas.
      declared: declaradasSet.has(nome),
      documents: num(o.files) || undefined,
      pathPrefix: `${prefixo}${nome}/`,
    });
  }

  const nomeAtual = (atual.name || '').toLowerCase();
  for (const p of (Array.isArray(projetos.projects) ? projetos.projects : []) as unknown[]) {
    const o = obj(p);
    const nome = str(o.name);
    if (!nome || nome.toLowerCase() === nomeAtual) continue;
    fontes.push({
      id: `project:${nome}`,
      kind: 'peer',
      name: nome,
      enabled: true,
      cloned: o.cloned === true,
      visibility: str(o.visibility) || undefined,
      status: str(o.status) || undefined,
      path: str(o.path) || undefined,
      scope: `project:${nome}`,
    });
  }

  return {
    sources: fontes,
    integrations: (Array.isArray(projetos.integrations) ? projetos.integrations : []).map(
      (i) => {
        const o = obj(i);
        return {
          from: str(o.from) || str(o.consumer) || '?',
          to: str(o.to) || str(o.provider) || '?',
          kind: str(o.kind) || 'http',
          name: str(o.name) || undefined,
        };
      },
    ),
    unresolved: lista(projetos.unresolved),
    divergences: (Array.isArray(projetos.divergences) ? projetos.divergences : []).map((d) =>
      typeof d === 'string' ? d : str(obj(d).message) || JSON.stringify(d).slice(0, 160),
    ),
    hubAvailable: Array.isArray(projetos.projects) && projetos.projects.length > 1,
  };
}

export function toAnalysis(d: Json): RequestAnalysis {
  const s = obj(d.scores);
  const dimensoes: Record<string, number> = {};
  for (const [k, v] of Object.entries(s)) {
    if (k === 'total' || k === 'raw_total') continue;
    if (typeof v === 'number') dimensoes[k] = v;
  }
  return {
    classification: str(d.classification) || 'UNKNOWN',
    complexity: str(d.complexity) || 'low',
    strategy: str(d.strategy) || 'EXECUTE',
    total: num(s.total),
    rawTotal: num(s.raw_total),
    confidence: num(d.confidence),
    reasoning: str(d.reasoning_summary),
    requiresDocumentation: bool(d.requires_documentation),
    requiresDecomposition: bool(d.requires_decomposition),
    requiresApproval: bool(d.requires_approval),
    scores: dimensoes,
    matchedSignals: lista(d.matched_signals),
    risks: lista(d.risks),
    dependencies: lista(d.dependencies),
    overriddenBy: str(d.overridden_by) || undefined,
    overrideReason: str(d.override_reason) || undefined,
  };
}

// ── grafo ───────────────────────────────────────────────────────────────
/**
 * Uma relação do `get_entity` vira uma aresta orientada do grafo.
 *
 * O servidor manda a aresta como ela existe no store (`src`/`dst`) e também o
 * nó do outro lado (`other`/`other_type`), que é o que a lista de relações
 * mostra. A tela de grafo precisa da PRIMEIRA leitura; ler a segunda como se
 * fosse a primeira é o bug que deixou o grafo do VS Code sem nenhuma aresta:
 * `rel.target` não existia, o código caía no `continue` e desenhava só nós
 * soltos.
 *
 * Por isso a tradução mora num lugar só, com teste de contrato dos dois lados.
 * A ordem de leitura é deliberada:
 *
 * 1. `src`/`dst` — o contrato canônico, igual à tabela `relations`.
 * 2. `other_id` + `direction` — como reconstruir a aresta num RAGX antigo,
 *    que ainda não manda `src`/`dst`. Sem isto, atualizar a extensão sem
 *    atualizar o RAGX voltaria a mostrar um grafo vazio.
 *
 * Devolve `undefined` quando não dá para saber quem são as duas pontas —
 * aresta sem destino não é aresta, e inventar um destino desenharia uma
 * ligação que não existe no projeto.
 */
export function toEdge(rel: unknown, centroId: string): GraphEdge | undefined {
  if (!rel || typeof rel !== 'object') return undefined;
  const r = rel as Json;

  const tipo = str(r.type) || 'related';
  const comum = {
    type: tipo,
    weight: typeof r.weight === 'number' ? r.weight : undefined,
    confidence: typeof r.confidence === 'number' ? r.confidence : undefined,
    // A procedência da ARESTA vai só como `tier`. O campo `source` da
    // `GraphEdge` é o nó de ORIGEM — pôr a procedência ali com o mesmo nome
    // sobrescreveria a ponta da aresta, que é o bug que este arquivo corrige.
    tier: toTier(r.tier),
  };

  // 1. contrato canônico
  const src = str(r.src) || str(r.src_id);
  const dst = str(r.dst) || str(r.dst_id);
  if (src && dst) return { ...comum, source: src, target: dst };

  // 2. compatibilidade: RAGX antigo mandava só o nó do outro lado
  const outro = str(r.other_id) || str(r.other) || str(r.target) || str(r.dst);
  if (!outro || !centroId) return undefined;
  const saindo = str(r.direction) !== 'in';
  return {
    ...comum,
    source: saindo ? centroId : outro,
    target: saindo ? outro : centroId,
  };
}

/** Tier desconhecido vira `undefined`: a UI não inventa um selo. */
export function toTier(v: unknown): 'extracted' | 'inferred' | undefined {
  return v === 'extracted' || v === 'inferred' ? v : undefined;
}

/**
 * As conversões contra saídas REAIS do RAGX.
 *
 * Toda amostra abaixo foi copiada da saída de `ragx <cmd> --json` ou de uma
 * ferramenta MCP deste repositório. Testar contra JSON inventado só prova que
 * o parser entende o que o próprio teste escreveu.
 */

import { describe, expect, it } from 'vitest';

import {
  toAnalysis,
  toChunk,
  toDocument,
  toSources,
  toTask,
  toTaskDetail,
  toTaskGraph,
  toTaskPanel,
} from '../../src/rag/parse';

// `ragx task analyze "migrar a autenticacao para SSO..." --json`
const ANALISE = {
  classification: 'SECURITY_CHANGE',
  complexity: 'high',
  requires_documentation: true,
  requires_decomposition: true,
  requires_approval: true,
  confidence: 0.66,
  reasoning_summary: 'altera a estrutura · toca autenticação · escopo amplo.',
  risks: ['toca autenticação'],
  dependencies: ['docs/adr/ADR-0011-federacao-entre-projetos.md'],
  scores: {
    complexity: 30, architecture: 40, business_rule: 0, dependency: 27,
    risk: 0, security: 65, documentation: 28, total: 57, raw_total: 57,
  },
  strategy: 'DOCUMENT -> DECOMPOSE -> EXECUTE',
  matched_signals: ['mudanca-estrutural', 'autenticacao', 'escopo-amplo'],
  overridden_by: null,
  override_reason: null,
};

// `ragx task status --json` num projeto sem plano de trabalho.
const PAINEL_VAZIO = {
  tasks: {},
  projects: [],
  knowledge: { documents: 312, chunks: 2473, entities: 1395, relations: 6380 },
  scheduler: { total: 0, enabled: 0, next: null },
};

// `ragx base list --json`
const BASE = {
  sources: [
    {
      name: 'agents',
      origin: './base-knowledge/agents',
      kind: 'path',
      ref: null,
      commit: null,
      added_at: '2026-09-15T17:46:50Z',
      updated_at: '2026-09-15T17:46:50Z',
      files: 36,
      enabled: true,
    },
  ],
};

describe('análise de pedido', () => {
  it('separa o total efetivo do bruto', () => {
    const a = toAnalysis(ANALISE);
    expect(a.classification).toBe('SECURITY_CHANGE');
    expect(a.total).toBe(57);
    expect(a.rawTotal).toBe(57);
    expect(a.requiresDecomposition).toBe(true);
    expect(a.matchedSignals).toContain('autenticacao');
  });

  it('não confunde `total` com uma dimensão', () => {
    // `total` e `raw_total` vêm DENTRO de `scores`. Desenhar uma barra de
    // "total" ao lado das sete dimensões mostraria uma oitava que não existe.
    const a = toAnalysis(ANALISE);
    expect(Object.keys(a.scores).sort()).toEqual([
      'architecture', 'business_rule', 'complexity', 'dependency',
      'documentation', 'risk', 'security',
    ]);
  });

  it('sobrevive a uma resposta sem nenhum campo', () => {
    const a = toAnalysis({});
    expect(a.classification).toBe('UNKNOWN');
    expect(a.scores).toEqual({});
    expect(a.risks).toEqual([]);
  });
});

describe('painel de tarefas', () => {
  it('projeto sem orquestração não é erro', () => {
    const p = toTaskPanel(PAINEL_VAZIO);
    expect(p.counts).toEqual({});
    expect(p.unavailable).toBeUndefined();
    expect(p.scheduler).toEqual({ total: 0, enabled: 0, next: null });
  });

  it('erro do banco de orquestração vira aviso, não exceção', () => {
    const p = toTaskPanel({ tasks: {}, tasks_error: 'no such table: tasks' });
    expect(p.unavailable).toContain('no such table');
  });
});

describe('tarefas', () => {
  it('lê o formato enxuto do `_slim`', () => {
    const t = toTask({
      id: 'T-001', project_id: 'P-1', title: 'Documentar o fluxo SSO',
      status: 'ready', priority: 'high', track: 'docs', type: 'documentation',
      requires_approval: false, acceptance_criteria: ['ADR escrita'],
      files_scope: ['docs/'], retry_count: 0,
    });
    expect(t.title).toBe('Documentar o fluxo SSO');
    expect(t.acceptanceCriteria).toEqual(['ADR escrita']);
  });

  it('aceita dependência como id puro ou como objeto', () => {
    const d = toTaskDetail({
      task: { id: 'T-2', title: 'x', status: 'blocked' },
      dependencies: ['T-1', { id: 'T-0', title: 'antes', status: 'completed' }],
      dependents: [],
    });
    expect(d.dependencies.map((r) => r.id)).toEqual(['T-1', 'T-0']);
    expect(d.dependencies[1].title).toBe('antes');
  });

  it('descarta aresta cujo nó não veio', () => {
    // A listagem tem teto. Uma aresta para um nó ausente desenharia uma seta
    // para o nada — pior que não desenhar.
    const g = toTaskGraph({
      nodes: [{ id: 'a', title: 'A', status: 'ready' }],
      edges: [
        { from: 'a', to: 'b', kind: 'depends_on' },
        { from: 'a', to: 'a', kind: 'depends_on' },
      ],
    });
    expect(g.edges).toHaveLength(1);
  });
});

describe('chunk', () => {
  it('lê o formato do MCP (lines/tokens)', () => {
    const c = toChunk({
      chunk_id: 'abc', lines: [10, 20], tokens: 144, kind: 'file',
      content: 'x', document_path: 'src/ragx/walk.py',
    });
    expect(c.lines).toEqual([10, 20]);
    expect(c.tokens).toBe(144);
    expect(c.documentPath).toBe('src/ragx/walk.py');
  });

  it('lê a linha crua do banco que a CLI imprime', () => {
    // `ragx chunk <id> --json` devolve a linha da tabela: `id`, `start_line`,
    // `end_line`, `token_count`. Sem aceitar as duas formas, o painel de
    // detalhe aparece vazio no transporte de reserva.
    const c = toChunk({
      id: '9e4e4d84', ordinal: 0, kind: 'file', symbol: null,
      heading_path: null, start_line: 1, end_line: 17,
      content: '"""FileWalker"""', token_count: 144, rel_path: 'src/ragx/walk.py',
    });
    expect(c.chunkId).toBe('9e4e4d84');
    expect(c.lines).toEqual([1, 17]);
    expect(c.tokens).toBe(144);
    expect(c.documentPath).toBe('src/ragx/walk.py');
  });
});

describe('documento', () => {
  it('aceita `path` do MCP e `rel_path` do banco', () => {
    expect(toDocument({ path: 'a.py', lang: 'python' }).path).toBe('a.py');
    expect(toDocument({ rel_path: '@base/agents/x.md', doc_kind: 'doc' }).path).toBe(
      '@base/agents/x.md',
    );
    // O banco guarda 0/1, não booleano.
    expect(toDocument({ rel_path: 'x', redacted: 1 }).redacted).toBe(true);
  });
});

describe('origens do conhecimento', () => {
  it('o projeto atual é sempre uma origem, mesmo sem hub nem base', () => {
    const o = toSources({}, {}, { name: 'ragx', documents: 312, chunks: 2473 });
    expect(o.sources).toHaveLength(1);
    expect(o.sources[0]).toMatchObject({ kind: 'project', name: 'ragx', scope: 'current' });
    expect(o.hubAvailable).toBe(false);
  });

  it('marca a fonte base instalada mas NÃO declarada', () => {
    // Instalar não basta: o projeto precisa declarar em `[base] sources`.
    // Sem esta marca a tela afirmaria que 36 arquivos estão neste índice
    // quando nenhum deles está.
    const declarada = toSources(BASE, {}, { name: 'ragx' }, ['agents']);
    const naoDeclarada = toSources(BASE, {}, { name: 'ragx' }, []);

    expect(declarada.sources[1]).toMatchObject({
      kind: 'base', name: 'agents', declared: true,
      pathPrefix: '@base/agents/', documents: 36,
    });
    expect(naoDeclarada.sources[1].declared).toBe(false);
  });

  it('usa `required_by_project` quando o transporte não passa a lista', () => {
    // O MCP já devolve as declaradas dentro da própria resposta; a CLI as lê
    // da configuração. As duas rotas têm de chegar ao mesmo resultado.
    const o = toSources(
      { ...BASE, required_by_project: ['agents'], prefix: '@base/' },
      {},
      { name: 'ragx' },
    );
    expect(o.sources[1].declared).toBe(true);
  });

  it('não lista o projeto atual duas vezes quando ele está no hub', () => {
    const o = toSources(
      {},
      { projects: [{ name: 'ragx' }, { name: 'outro', cloned: false, visibility: 'public' }] },
      { name: 'ragx' },
    );
    expect(o.sources.filter((s) => s.name === 'ragx')).toHaveLength(1);
    expect(o.sources[1]).toMatchObject({ kind: 'peer', name: 'outro', scope: 'project:outro' });
  });

  it('contagem ausente é `undefined`, nunca zero', () => {
    // Zero é uma afirmação sobre o índice. "Não sei" é a verdade quando o
    // projeto do hub nem está clonado nesta máquina.
    const o = toSources({}, { projects: [{ name: 'p' }, { name: 'q' }] }, { name: 'p' });
    expect(o.sources[1].documents).toBeUndefined();
  });
});

/**
 * Contrato do grafo: uma relação do RAGX vira uma aresta desenhável.
 *
 * O bug que este arquivo existe para impedir: o servidor mandava `other` e
 * `other_type`, o cliente lia `target` e `dst`, nenhum dos dois casava, e o
 * grafo do VS Code aparecia só com nós soltos — sem uma única aresta. Nada
 * quebrava, nada aparecia no log: a tela simplesmente mentia sobre o projeto.
 *
 * O par deste arquivo é `tests/unit/test_contrato_grafo.py`, que fixa o que o
 * servidor MANDA. Os dois juntos fecham o ciclo — um garante o formato de
 * saída, o outro garante que este cliente o entende.
 */

import { describe, expect, it } from 'vitest';

import { toEdge, toProvenance } from '../../src/rag/parse';

/** Uma relação como o `get_entity` do RAGX a devolve hoje. */
function relacao(over: Record<string, unknown> = {}) {
  return {
    direction: 'out',
    type: 'imports',
    src: 'id-A',
    dst: 'id-B',
    other: 'B',
    other_id: 'id-B',
    other_type: 'class',
    other_qualified_name: 'src/b.py::B',
    weight: 1.0,
    confidence: 0.8,
    provenance: 'reference',
    ...over,
  };
}

describe('aresta orientada', () => {
  it('A -> B vira uma aresta de A para B', () => {
    const e = toEdge(relacao(), 'id-A');
    expect(e).toEqual({
      source: 'id-A',
      target: 'id-B',
      type: 'imports',
      weight: 1.0,
      confidence: 0.8,
      provenance: 'reference',
    });
  });

  it('a direção vem do contrato, não de quem perguntou', () => {
    // `src`/`dst` já são orientados: mesmo perguntando a partir de B, a aresta
    // continua saindo de A. Inverter aqui desenharia a dependência ao contrário.
    const e = toEdge(relacao({ direction: 'in' }), 'id-B');
    expect(e?.source).toBe('id-A');
    expect(e?.target).toBe('id-B');
  });

  it('preserva confidence e provenance sem perda', () => {
    for (const p of ['structural', 'reference', 'semantic'] as const) {
      const e = toEdge(relacao({ provenance: p, confidence: 0.42 }), 'id-A');
      expect(e?.provenance).toBe(p);
      expect(e?.confidence).toBe(0.42);
    }
  });

  it('confidence 0 é ZERO, não "ausente"', () => {
    // O descuido clássico: `x || undefined` transforma 0 em undefined e a UI
    // mostra "sem informação" onde o RAGX disse "confiança nenhuma".
    expect(toEdge(relacao({ confidence: 0 }), 'id-A')?.confidence).toBe(0);
  });

  it('provenance desconhecida vira undefined em vez de virar selo inventado', () => {
    expect(toEdge(relacao({ provenance: 'chutometro' }), 'id-A')?.provenance).toBeUndefined();
    expect(toProvenance(null)).toBeUndefined();
    expect(toProvenance('structural')).toBe('structural');
  });
});

describe('compatibilidade com RAGX antigo', () => {
  it('sem src/dst, reconstrói a aresta a partir de other_id + direction', () => {
    const antigo = { direction: 'out', type: 'calls', other: 'B', other_id: 'id-B' };
    expect(toEdge(antigo, 'id-A')).toMatchObject({ source: 'id-A', target: 'id-B' });
  });

  it('direction "in" inverte a aresta reconstruída', () => {
    const antigo = { direction: 'in', type: 'calls', other: 'B', other_id: 'id-B' };
    expect(toEdge(antigo, 'id-A')).toMatchObject({ source: 'id-B', target: 'id-A' });
  });

  it('sem other_id, cai no nome — melhor um grafo por nome que nenhum grafo', () => {
    const antigo = { direction: 'out', type: 'calls', other: 'B' };
    expect(toEdge(antigo, 'id-A')).toMatchObject({ source: 'id-A', target: 'B' });
  });
});

describe('casos extremos', () => {
  it('relação sem destino NÃO vira aresta', () => {
    // Inventar um destino desenharia uma ligação que não existe no projeto.
    expect(toEdge({ direction: 'out', type: 'calls' }, 'id-A')).toBeUndefined();
    expect(toEdge({}, 'id-A')).toBeUndefined();
  });

  it('entrada malformada devolve undefined em vez de explodir', () => {
    for (const lixo of [null, undefined, 42, 'texto', []]) {
      expect(() => toEdge(lixo, 'id-A')).not.toThrow();
      expect(toEdge(lixo, 'id-A')).toBeUndefined();
    }
  });

  it('auto-referência é aresta legítima (recursão existe)', () => {
    const e = toEdge(relacao({ src: 'id-A', dst: 'id-A', other_id: 'id-A' }), 'id-A');
    expect(e).toMatchObject({ source: 'id-A', target: 'id-A' });
  });

  it('tipo ausente vira "related", nunca string vazia', () => {
    expect(toEdge(relacao({ type: undefined }), 'id-A')?.type).toBe('related');
  });

  it('arestas duplicadas são preservadas — quem deduplica é a camada de cima', () => {
    const rs = [relacao(), relacao()];
    const es = rs.map((r) => toEdge(r, 'id-A'));
    expect(es).toHaveLength(2);
    expect(es[0]).toEqual(es[1]);
  });

  it('múltiplas arestas entre os mesmos nós com tipos diferentes coexistem', () => {
    const a = toEdge(relacao({ type: 'imports' }), 'id-A');
    const b = toEdge(relacao({ type: 'calls' }), 'id-A');
    expect(a?.type).not.toBe(b?.type);
    expect(a?.source).toBe(b?.source);
  });

  it('grafo vazio devolve lista vazia, não erro', () => {
    const es = ([] as unknown[]).map((r) => toEdge(r, 'id-A')).filter(Boolean);
    expect(es).toEqual([]);
  });

  it('grafo grande mantém todas as arestas', () => {
    const rs = Array.from({ length: 5000 }, (_, i) =>
      relacao({ dst: `id-${i}`, other_id: `id-${i}` }),
    );
    const es = rs.map((r) => toEdge(r, 'id-A')).filter(Boolean);
    expect(es).toHaveLength(5000);
    expect(new Set(es.map((e) => e!.target)).size).toBe(5000);
  });
});

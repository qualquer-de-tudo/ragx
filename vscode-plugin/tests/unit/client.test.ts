/**
 * O `RagClient` contra saídas REAIS do RAGX.
 *
 * As amostras abaixo foram copiadas da saída de `ragx <cmd> --json` neste
 * repositório. Testar contra JSON inventado só prova que o parser entende o
 * que o próprio teste escreveu.
 */

import { execFile } from 'node:child_process';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CliRagClient } from '../../src/rag/CliClient';
import { humanize, propagate } from '../../src/rag/RagClient';

vi.mock('node:child_process', () => ({ execFile: vi.fn() }));

// Sem isto, `mock.calls[0]` traz a chamada de um teste anterior e a asserção
// sobre argumentos verifica a coisa errada — passando por acidente.
beforeEach(() => vi.mocked(execFile).mockClear());

/**
 * Instala uma implementação para o `execFile` mockado.
 *
 * O callback é localizado pelo TIPO, não pela posição: `promisify` monta a
 * chamada como `(cmd, args, opts, cb)`, mas o `execFile` real tem sobrecargas
 * em que `opts` some. Fixar o índice faz o mock quebrar com "cb is not a
 * function" sempre que a convenção muda.
 */
function instalar(fn: (args: string[]) => { erro?: unknown; stdout?: string }): void {
  vi.mocked(execFile).mockImplementation(((...todos: unknown[]) => {
    const cb = todos.find((a) => typeof a === 'function') as
      | ((e: unknown, r?: { stdout: string; stderr: string }) => void)
      | undefined;
    const args = (todos[1] as string[]) ?? [];
    const r = fn(args);
    cb?.(r.erro ?? null, { stdout: r.stdout ?? '', stderr: '' });
    return {} as never;
  }) as never);
}

/** O próximo `execFile` devolve este stdout. */
function responde(stdout: string): void {
  instalar(() => ({ stdout }));
}

/** O próximo `execFile` falha com este erro. */
function falha(erro: NodeJS.ErrnoException): void {
  instalar(() => ({ erro }));
}

const cliente = () => new CliRagClient({ command: 'ragx', cwd: '/proj' });

const STATUS_REAL = JSON.stringify({
  initialized: true,
  documents: 312,
  chunks: 2473,
  by_lang: { markdown: 164, python: 129, yaml: 7 },
  security_events: 20,
  embeddings: 2473,
  embedding_model: {
    id: 'fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
    dim: 384,
    versioned_dim: 192,
  },
  last_run: {
    id: 17,
    mode: 'incremental',
    started_at: '2026-09-15T18:19:31Z',
    finished_at: '2026-09-15T18:19:40Z',
    files_seen: 13186,
    indexed: 2,
    blocked: 18,
    duration_ms: 8600,
  },
});

const BUSCA_REAL = JSON.stringify({
  query: 'autenticacao',
  mode: 'hybrid',
  degraded: null,
  timings_ms: { keyword: 1.95, semantic: 2225.52, fusion: 0.04 },
  results: [
    {
      chunk_id: 'c6e72da642b7f927b5e55ab364d1da86',
      project: 'current',
      document_path: 'src/ragx/security/gate.py',
      symbol: 'SecurityGate',
      heading_path: null,
      kind: 'class',
      lines: [34, 116],
      score: 0.0312,
      content: 'class SecurityGate:',
      matched_by: ['keyword', 'semantic'],
    },
  ],
});

describe('CliRagClient.stats', () => {
  it('lê a saída real de `ragx status --json`', async () => {
    responde(STATUS_REAL);
    const r = await cliente().stats();
    expect(r.ok).toBe(true);
    expect(r.data?.documents).toBe(312);
    expect(r.data?.chunks).toBe(2473);
    expect(r.data?.embeddingModel?.dim).toBe(384);
    expect(r.data?.lastRun?.blocked).toBe(18);
    expect(r.data?.byLang.markdown).toBe(164);
  });
});

describe('CliRagClient.search', () => {
  it('converte resultados preservando `matched_by`', async () => {
    responde(BUSCA_REAL);
    const r = await cliente().search('autenticacao', 'hybrid', 10);
    expect(r.ok).toBe(true);
    const hit = r.data!.results[0];
    expect(hit.documentPath).toBe('src/ragx/security/gate.py');
    expect(hit.lines).toEqual([34, 116]);
    // `keyword` é o que separa uma correspondência literal de uma coincidência
    // semântica — a UI mostra isso, então o parser não pode perder.
    expect(hit.matchedBy).toContain('keyword');
  });

  it('aplica o filtro de score mínimo no cliente', async () => {
    responde(BUSCA_REAL);
    const r = await cliente().search('x', 'hybrid', 10, { minScore: 0.5 });
    expect(r.data?.results).toHaveLength(0);
  });
});

describe('ruído antes do JSON', () => {
  it('ignora aviso de biblioteca impresso antes da saída', async () => {
    // O fastembed imprime um UserWarning ao carregar o modelo. Sem isto, todo
    // primeiro comando da sessão falharia com erro de parse.
    responde(
      'UserWarning: The model now uses mean pooling instead of CLS\n' + STATUS_REAL,
    );
    const r = await cliente().stats();
    expect(r.ok).toBe(true);
    expect(r.data?.documents).toBe(312);
  });
});

describe('falhas', () => {
  it('comando ausente vira `spawn_failed` com orientação', async () => {
    const e = new Error('spawn ragx ENOENT') as NodeJS.ErrnoException;
    e.code = 'ENOENT';
    falha(e);
    const r = await cliente().stats();
    expect(r.ok).toBe(false);
    expect(r.error?.code).toBe('spawn_failed');
    expect(humanize(r.error!).actions).toContain('settings');
  });

  it('timeout vira `timeout`', async () => {
    const e = new Error('timeout') as NodeJS.ErrnoException & { killed: boolean };
    e.killed = true;
    falha(e);
    const r = await cliente().stats();
    expect(r.error?.code).toBe('timeout');
  });

  it('arquivo não indexado NÃO vira erro — vira ausência declarada', async () => {
    const e = new Error('nao existe') as NodeJS.ErrnoException;
    e.code = '1';
    falha(e);
    const r = await cliente().fileKnowledge('.env');
    // O .env não estar no índice é o comportamento correto, não uma falha. A
    // UI precisa poder dizer isso sem parecer que algo quebrou.
    expect(r.ok).toBe(true);
    expect(r.data?.indexed).toBe(false);
    expect(r.data?.reason).toContain('Security Gate');
  });
});

describe('segurança do transporte', () => {
  it('sync usa o incremental, nunca reindexação completa', async () => {
    responde(JSON.stringify({ indexed: 3, blocked: 0, warnings: [] }));
    await cliente().sync();
    const args = vi.mocked(execFile).mock.calls[0]![1] as string[];
    expect(args).toContain('watch');
    expect(args).toContain('--once');
    // `index --full` a cada save reindexaria o repositório inteiro (§48).
    expect(args).not.toContain('--full');
  });

  it('a varredura de segurança agrega por REGRA, sem expor caminhos', async () => {
    responde(
      JSON.stringify({
        policy: 'strict',
        rules: 28,
        blocked: [
          { rel_path: 'tests/fixtures/.env', rule_id: 'filename-deny:env' },
          { rel_path: 'app/secrets.json', rule_id: 'filename-deny:env' },
          { rel_path: 'k.pem', rule_id: 'filename-deny:pem' },
        ],
        redacted: [],
      }),
    );
    const r = await cliente().security();
    expect(r.ok).toBe(true);
    expect(r.data?.blockedFiles).toBe(3);

    // A lista de arquivos bloqueados é um mapa de onde estão os segredos —
    // nunca sai do cliente (§19).
    const serializado = JSON.stringify(r.data);
    expect(serializado).not.toContain('.env');
    expect(serializado).not.toContain('secrets.json');
    expect(serializado).not.toContain('.pem');
    expect(r.data?.reasons).toEqual([
      { rule: 'filename-deny:env', count: 2 },
      { rule: 'filename-deny:pem', count: 1 },
    ]);
  });
});

describe('CliRagClient — os argumentos que vão para a CLI', () => {
  /**
   * Estes testes existem por causa de dois bugs reais.
   *
   * O cliente chamava `ragx documents --filter <x>` e `ragx chunks <caminho>`.
   * Nenhuma das duas formas existe: a flag é `--path` e o caminho vai em
   * `--document`. O Typer recusava, o `execFile` falhava, e a UI mostrava
   * "não indexado" — acusando o Security Gate de um bloqueio que nunca houve.
   *
   * Um teste sobre o RESULTADO não pegaria isso: a resposta de erro era
   * plausível. Só verificar o argv pega.
   *
   * O par deste teste está em `tests/unit/test_plugin_contrato.py`, que
   * confere os mesmos comandos contra a CLI de verdade.
   */
  const argv = async (fn: (c: CliRagClient) => Promise<unknown>, stdout = '[]') => {
    instalar(() => ({ stdout }));
    // Limpa DEPOIS de instalar: várias asserções por teste, e `calls[0]`
    // traria a chamada anterior — o teste passaria verificando outra coisa.
    vi.mocked(execFile).mockClear();
    await fn(cliente());
    return (vi.mocked(execFile).mock.calls[0]?.[1] as string[]) ?? [];
  };

  it('lista documentos com `--path` e curinga', async () => {
    const args = await argv((c) => c.documents('@base/agents/'));
    expect(args[0]).toBe('documents');
    expect(args).toContain('--path');
    // Sem `*`, o LIKE do SQLite casa só com o caminho inteiro e devolve vazio.
    expect(args[args.indexOf('--path') + 1]).toBe('*@base/agents/*');
    expect(args).not.toContain('--filter');
  });

  it('não duplica o curinga de quem já escreveu um glob', async () => {
    const args = await argv((c) => c.documents('src/*.py'));
    expect(args[args.indexOf('--path') + 1]).toBe('src/*.py');
  });

  it('pede os chunks de um documento por `--document`', async () => {
    const args = await argv((c) => c.fileKnowledge('src/ragx/walk.py'));
    expect(args.slice(0, 3)).toEqual(['chunks', '--document', 'src/ragx/walk.py']);
  });

  it('busca com escopo só quando ele não é o padrão', async () => {
    const semEscopo = await argv(
      (c) => c.search('x', 'hybrid', 5, { scope: 'current' }),
      '{"results":[]}',
    );
    expect(semEscopo).not.toContain('--scope');

    const comEscopo = await argv(
      (c) => c.search('x', 'hybrid', 5, { scope: 'project:outro' }),
      '{"results":[]}',
    );
    expect(comEscopo[comEscopo.indexOf('--scope') + 1]).toBe('project:outro');
  });

  it('usa os subcomandos de tarefa que existem', async () => {
    expect((await argv((c) => c.tasks())).slice(0, 2)).toEqual(['task', 'list']);
    expect((await argv((c) => c.task('T-1'))).slice(0, 3)).toEqual(['task', 'show', 'T-1']);
    expect((await argv((c) => c.taskGraph())).slice(0, 2)).toEqual(['task', 'graph']);
    expect((await argv((c) => c.taskPanel(), '{}')).slice(0, 2)).toEqual(['task', 'status']);
    expect((await argv((c) => c.analyzeRequest('fazer x'), '{}')).slice(0, 3)).toEqual([
      'task', 'analyze', 'fazer x',
    ]);
    expect((await argv((c) => c.chunk('abc'), '{}')).slice(0, 2)).toEqual(['chunk', 'abc']);
  });

  it('projeto sem orquestração não vira erro de tela', async () => {
    // `ragx task status` falha quando o banco de orquestração não existe —
    // e não ter plano de trabalho é o estado normal de quase todo projeto.
    falha(Object.assign(new Error('no such table: tasks'), { stderr: 'no such table' }));
    const r = await cliente().taskPanel();
    expect(r.ok).toBe(true);
    expect(r.data?.unavailable).toBeTruthy();
  });
});

describe('propagate', () => {
  it('repassa a falha mudando só o tipo', () => {
    const r = propagate<number>({ ok: false, error: { code: 'x', message: 'y' } });
    expect(r.ok).toBe(false);
    expect(r.error).toEqual({ code: 'x', message: 'y' });
    expect(r.data).toBeUndefined();
  });

  it('nunca devolve `ok: true` sem dado', () => {
    const r = propagate<number>({ ok: false });
    expect(r.ok).toBe(false);
    expect(r.error?.message).toBeTruthy();
  });
});

describe('humanize', () => {
  it('não devolve stack trace, e sempre oferece uma saída', () => {
    for (const code of ['not_found', 'spawn_failed', 'no_project', 'timeout', 'qualquer']) {
      const h = humanize({ code, message: 'Traceback (most recent call last): ...' });
      expect(h.title).not.toContain('Traceback');
      expect(h.reason).not.toContain('Traceback');
      expect(h.title.length).toBeGreaterThan(3);
    }
  });
});

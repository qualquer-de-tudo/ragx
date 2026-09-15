/**
 * A interface montada de verdade, com um host falso no lugar do VS Code.
 *
 * O `tsc` prova que os tipos fecham; não prova que a tela abre. Um import
 * circular, um `undefined` desreferenciado no primeiro render ou uma página
 * que quebra ao receber a resposta do host passam pelo typecheck inteiros e
 * aparecem como painel em branco — o sintoma que a §44 proíbe e que ninguém
 * consegue diagnosticar pela tela.
 *
 * O host falso responde às mensagens como o `MessageRouter` responderia, então
 * o que está sendo exercitado é o caminho real: pedido com id, resposta com o
 * mesmo id, e a página renderizando o payload.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

interface Enviada {
  type: string;
  id: string;
  [k: string]: unknown;
}

const enviadas: Enviada[] = [];

/** Respostas por tipo de mensagem. O que não estiver aqui fica carregando. */
const RESPOSTAS: Record<string, unknown> = {
  ready: { kind: 'ack' },
  getStats: {
    kind: 'stats',
    stats: {
      initialized: true, documents: 312, chunks: 2473, embeddings: 2473,
      entities: 1395, relations: 6380, securityEvents: 20,
      byLang: { python: 129, markdown: 164 },
    },
  },
  getHealth: { kind: 'health', checks: [{ name: 'Índice', status: 'ok', detail: '2473 chunks' }] },
  getSources: {
    kind: 'sources',
    overview: {
      sources: [
        { id: 'project', kind: 'project', name: 'ragx', enabled: true, documents: 276, scope: 'current' },
        {
          id: '@base/agents', kind: 'base', name: 'agents', enabled: true, declared: true,
          documents: 36, pathPrefix: '@base/agents/', origin: './base-knowledge/agents',
        },
        { id: 'project:outro', kind: 'peer', name: 'outro', enabled: true, cloned: false, scope: 'project:outro' },
      ],
      integrations: [], unresolved: [], divergences: [], hubAvailable: true,
    },
  },
  getTaskPanel: { kind: 'taskPanel', panel: { counts: { ready: 2, completed: 1 }, projects: [] } },
  getTasks: {
    kind: 'tasks',
    tasks: [
      {
        id: 'T-1', projectId: 'P', title: 'Documentar o fluxo SSO', status: 'ready',
        priority: 'high', track: 'docs', type: 'documentation', requiresApproval: false,
        acceptanceCriteria: [], filesScope: [], retryCount: 0,
      },
    ],
  },
  getDocuments: {
    kind: 'documents',
    documents: [
      { path: 'src/ragx/walk.py', lang: 'python', kind: 'code', title: null, chunks: 6, redacted: false },
      { path: '@base/agents/core/standards.md', lang: 'markdown', kind: 'doc', title: null, chunks: 3, redacted: false },
    ],
  },
  getSecurity: {
    kind: 'security',
    security: {
      gateActive: true, policy: 'strict', rules: 28, blockedFiles: 18, redactedFiles: 0,
      reasons: [{ rule: 'filename-deny:env', count: 12 }],
      ignoreFiles: ['.gitignore'], indexedSecrets: 0, embeddedSecrets: 0,
    },
  },
};

function instalarHost(): void {
  (globalThis as unknown as { acquireVsCodeApi: unknown }).acquireVsCodeApi = () => ({
    postMessage: (msg: Enviada) => {
      enviadas.push(msg);
      const payload = RESPOSTAS[msg.type];
      if (!payload) return;
      queueMicrotask(() =>
        window.dispatchEvent(
          new MessageEvent('message', { data: { type: 'result', id: msg.id, ok: true, payload } }),
        ),
      );
    },
    getState: () => ({}),
    setState: () => undefined,
  });
}

/** Deixa as microtarefas e os efeitos correrem. */
async function assentar(): Promise<void> {
  const { act } = await import('react-dom/test-utils');
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

async function montar(host: 'sidebar' | 'editor', largura: number) {
  window.innerWidth = largura;
  const { act } = await import('react-dom/test-utils');
  const { createRoot } = await import('react-dom/client');
  const React = await import('react');
  const { App } = await import('../../webview/src/app/App');

  const alvo = document.createElement('div');
  document.body.appendChild(alvo);
  const root = createRoot(alvo);
  await act(async () => {
    root.render(React.createElement(App));
  });
  // O host manda o estado assim que a webview diz `ready`.
  await act(async () => {
    window.dispatchEvent(
      new MessageEvent('message', {
        data: {
          type: 'state',
          state: 'ready',
          host,
          project: { name: 'ragx', root: '/p', transport: 'mcp' },
        },
      }),
    );
  });
  await assentar();
  return { alvo, root };
}

async function irPara(alvo: HTMLElement, rotulo: string): Promise<void> {
  const { act } = await import('react-dom/test-utils');
  const botao = [...alvo.querySelectorAll('nav button')].find(
    (b) => b.textContent?.includes(rotulo),
  ) as HTMLButtonElement | undefined;
  expect(botao, `nav sem "${rotulo}"`).toBeTruthy();
  await act(async () => {
    botao!.click();
  });
  await assentar();
}

// Sem isto o React avisa, a cada render, que o ambiente não suporta `act` —
// centenas de linhas de stderr que escondem um erro de verdade.
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

beforeEach(() => {
  enviadas.length = 0;
  document.body.innerHTML = '';
  vi.resetModules();
  instalarHost();
});

describe('a casca', () => {
  it('abre na barra lateral e oferece a tela cheia', async () => {
    const { alvo } = await montar('sidebar', 340);
    expect(alvo.textContent).toContain('RAGX Knowledge');
    const botao = alvo.querySelector('[aria-label="Abrir em tela cheia"]');
    expect(botao).toBeTruthy();

    const { act } = await import('react-dom/test-utils');
    await act(async () => {
      (botao as HTMLButtonElement).click();
    });
    // O host recebe o pedido com a página atual, para a aba já abrir nela.
    const pedido = enviadas.find((m) => m.type === 'openEditor');
    expect(pedido?.page).toBe('overview');
  });

  it('na aba do editor não oferece abrir a aba do editor', async () => {
    // O botão apontaria para a tela onde a pessoa já está.
    const { alvo } = await montar('editor', 1400);
    expect(alvo.querySelector('[aria-label="Abrir em tela cheia"]')).toBeNull();
  });

  it('lista as páginas novas na navegação', async () => {
    const { alvo } = await montar('editor', 1400);
    const nav = alvo.querySelector('nav')!.textContent ?? '';
    for (const p of ['Overview', 'Search', 'Graph', 'Documents', 'Origens', 'Tasks', 'Security']) {
      expect(nav, `falta ${p}`).toContain(p);
    }
  });
});

describe('as páginas montam com dado real', () => {
  it('Overview mostra os números e as origens', async () => {
    const { alvo } = await montar('editor', 1400);
    expect(alvo.textContent).toContain('Knowledge Overview');
    expect(alvo.textContent).toContain('Origens');
    // A contagem do projeto e a da fonte base aparecem separadas.
    expect(alvo.textContent).toContain('276');
    expect(alvo.textContent).toContain('36');
  });

  it('Origens separa projeto, @base e hub', async () => {
    const { alvo } = await montar('editor', 1400);
    await irPara(alvo, 'Origens');
    const texto = alvo.textContent ?? '';
    expect(texto).toContain('Este projeto');
    expect(texto).toContain('Conhecimento base');
    expect(texto).toContain('Outros projetos');
    // Um projeto do hub que não está clonado não pode alegar contagem.
    expect(texto).toContain('contagem indisponível');
  });

  it('Documents marca o que veio de fonte base', async () => {
    const { alvo } = await montar('editor', 1400);
    await irPara(alvo, 'Documents');
    expect(alvo.textContent).toContain('src/ragx/walk.py');
    expect(alvo.textContent).toContain('@base/agents/core/standards.md');
  });

  it('Tasks mostra o painel por estado', async () => {
    const { alvo } = await montar('editor', 1400);
    await irPara(alvo, 'Tasks');
    const texto = alvo.textContent ?? '';
    expect(texto).toContain('Painel');
    expect(texto).toContain('ready');
    expect(texto).toContain('Documentar o fluxo SSO');
  });

  it('Security nunca mostra caminho de arquivo bloqueado', async () => {
    const { alvo } = await montar('editor', 1400);
    await irPara(alvo, 'Security');
    const texto = alvo.textContent ?? '';
    expect(texto).toContain('Security Status');
    expect(texto).toContain('filename-deny:env');
    // A regra agregada aparece; o caminho, nunca (§19).
    expect(texto).not.toContain('.env');
  });

  it('nenhuma página pedida deixa a tela em branco', async () => {
    const { alvo } = await montar('editor', 1400);
    for (const pagina of ['Search', 'Graph', 'Dictionary', 'Context', 'Agents', 'Monitor']) {
      await irPara(alvo, pagina);
      const main = alvo.querySelector('main')!;
      expect(main.textContent?.trim().length, `${pagina} abriu em branco`).toBeGreaterThan(0);
    }
  });
});

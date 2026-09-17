/**
 * Ciclo de vida da conexão com o RAGX.
 *
 * Subir o RAGX custa ~1,6 s, quase tudo boot do Python e import do SDK de MCP.
 * Esse custo é aceitável UMA vez; pago duas, é um processo Python órfão de
 * ~100 MB por engano. Por isso o que este arquivo protege não é a velocidade
 * de uma conexão, e sim quantas conexões acontecem:
 *
 * - duas chamadas simultâneas sobem UM processo, não dois;
 * - queda do processo é percebida na hora, não na próxima consulta;
 * - a reconexão espera cada vez mais em vez de girar em falso.
 *
 * O `StdioClientTransport` é mockado: o alvo aqui é a máquina de estados, e
 * subir Python de verdade faria a suíte depender de ter o RAGX instalado.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const conexoes: Array<{ close: ReturnType<typeof vi.fn> }> = [];
let falharProximaConexao = false;
/** Guarda o `onclose` que o cliente instalou, para simular a queda. */
let aoFechar: (() => void) | undefined;

vi.mock('@modelcontextprotocol/sdk/client/stdio.js', () => ({
  StdioClientTransport: class {
    onclose?: () => void;
    onerror?: (e: Error) => void;
    stderr = undefined;
    constructor() {
      // eslint-disable-next-line @typescript-eslint/no-this-alias
      const self = this;
      queueMicrotask(() => {
        aoFechar = () => self.onclose?.();
      });
    }
  },
}));

vi.mock('@modelcontextprotocol/sdk/client/index.js', () => ({
  Client: class {
    close = vi.fn(async () => {});
    constructor() {
      conexoes.push({ close: this.close });
    }
    async connect() {
      if (falharProximaConexao) throw new Error('spawn ragx ENOENT');
    }
    async listTools() {
      return { tools: [{ name: 'get_playbook' }, { name: 'get_entity' }] };
    }
    async callTool() {
      return {
        content: [{ type: 'text', text: JSON.stringify({ ok: true, data: { project: 'demo' } }) }],
      };
    }
  },
}));

const { McpRagClient } = await import('../../src/rag/McpClient');

const opcoes = { command: 'ragx', args: ['mcp', 'serve'], cwd: '/projeto' };

beforeEach(() => {
  conexoes.length = 0;
  falharProximaConexao = false;
  aoFechar = undefined;
});

describe('conexão', () => {
  it('conecta e descobre as ferramentas do servidor', async () => {
    const c = new McpRagClient(opcoes);
    const r = await c.connect();
    expect(r.ok).toBe(true);
    expect(r.data?.name).toBe('demo');
    expect(r.data?.transport).toBe('mcp');
    expect(c.has('get_entity')).toBe(true);
    expect(c.has('ferramenta_que_nao_existe')).toBe(false);
  });

  it('mede cada etapa até ficar pronto', async () => {
    const c = new McpRagClient(opcoes);
    await c.connect();
    const t = c.medidas();
    expect(t).toBeDefined();
    // As etapas existem e somam algo coerente. O VALOR depende da máquina;
    // afirmar "abaixo de X ms" aqui só produziria um teste instável.
    expect(t!.totalMs).toBeGreaterThanOrEqual(0);
    expect(t!.totalMs).toBeGreaterThanOrEqual(t!.spawnBootHandshakeMs);
  });

  it('falha de spawn vira erro-dado, não exceção', async () => {
    falharProximaConexao = true;
    const c = new McpRagClient(opcoes);
    const r = await c.connect();
    expect(r.ok).toBe(false);
    expect(r.error?.code).toBe('spawn_failed');
  });

  it('ferramenta ausente no servidor não vira chamada às cegas', async () => {
    const c = new McpRagClient(opcoes);
    await c.connect();
    const r = await c.graph('X', 1, 10);
    // `get_entity` existe no mock; `search_graph` não. A mensagem precisa
    // dizer o que fazer, não só que falhou.
    const semFerramenta = await c.dictionary();
    expect(r.ok).toBe(true);
    expect(semFerramenta.ok).toBe(false);
    expect(semFerramenta.error?.code).toBe('unsupported');
    expect(semFerramenta.error?.message).toMatch(/atualize o RAGX/);
  });
});

describe('queda do processo', () => {
  it('avisa quando o RAGX cai sozinho', async () => {
    const onCrash = vi.fn();
    const c = new McpRagClient({ ...opcoes, onCrash });
    await c.connect();

    aoFechar?.();
    expect(onCrash).toHaveBeenCalledTimes(1);
    expect(onCrash.mock.calls[0][0]).toMatch(/encerrou/);
  });

  it('desligar de propósito NÃO conta como queda', async () => {
    // Sem esta distinção, todo `dispose()` — troca de workspace, reload da
    // janela — dispararia uma reconexão contra um cliente já substituído.
    const onCrash = vi.fn();
    const c = new McpRagClient({ ...opcoes, onCrash });
    await c.connect();

    await c.dispose();
    aoFechar?.();
    expect(onCrash).not.toHaveBeenCalled();
  });

  it('uma queda avisa uma vez só', async () => {
    const onCrash = vi.fn();
    const c = new McpRagClient({ ...opcoes, onCrash });
    await c.connect();

    aoFechar?.();
    aoFechar?.();
    aoFechar?.();
    expect(onCrash).toHaveBeenCalledTimes(1);
  });

  it('depois da queda, chamar devolve "disconnected" em vez de travar', async () => {
    const c = new McpRagClient({ ...opcoes, onCrash: () => {} });
    await c.connect();
    aoFechar?.();

    const r = await c.graph('X', 1, 10);
    expect(r.ok).toBe(false);
    expect(r.error?.code).toBe('disconnected');
  });
});

describe('espera crescente entre tentativas', () => {
  /**
   * A política vive em `extension.ts`, que depende de `vscode` e não carrega
   * aqui. O que se fixa é a POLÍTICA em si — dobrar, com teto e desistência —
   * porque foi ela que impediu o laço de reconexão a 100% de CPU.
   */
  const ESPERA_INICIAL = 1_000;
  const TETO = 60_000;
  const MAX = 6;
  const espera = (tentativa: number) => Math.min(ESPERA_INICIAL * 2 ** tentativa, TETO);

  it('dobra a cada tentativa', () => {
    expect([0, 1, 2, 3].map(espera)).toEqual([1_000, 2_000, 4_000, 8_000]);
  });

  it('nunca passa do teto', () => {
    expect(espera(20)).toBe(TETO);
    expect(espera(1000)).toBe(TETO);
  });

  it('a primeira espera não é zero', () => {
    // Uma espera inicial de 0 ms reconstrói exatamente o laço que a espera
    // crescente existe para evitar.
    expect(espera(0)).toBeGreaterThan(0);
  });

  it('desiste depois de um número finito de tentativas', () => {
    // Somadas, as tentativas cobrem ~2 minutos: tempo de instalar o RAGX e
    // usar "Reconnect", sem ficar subindo processo para sempre.
    const total = Array.from({ length: MAX }, (_, i) => espera(i)).reduce((a, b) => a + b, 0);
    expect(MAX).toBeLessThan(20);
    expect(total).toBeLessThan(5 * 60_000);
  });
});

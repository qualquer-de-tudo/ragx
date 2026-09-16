/**
 * O teto de `limit` do RAGX é um CONTRATO, não uma sugestão.
 *
 * O `SearchRequest` do servidor recusa `limit > 50` com ValidationError em vez
 * de truncar. O inventário de documentos pedia 100 quando caía na derivação
 * por busca, e a aba Documents quebrava inteira em instalações do RAGX sem
 * `list_documents`. Este teste existe para que o pedido nunca volte a passar
 * do que o servidor aceita.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const chamadas: Array<{ name: string; arguments: Record<string, unknown> }> = [];
let ferramentas: string[] = [];

vi.mock('@modelcontextprotocol/sdk/client/stdio.js', () => ({
  StdioClientTransport: class {
    stderr = undefined;
  },
}));

vi.mock('@modelcontextprotocol/sdk/client/index.js', () => ({
  Client: class {
    async connect(): Promise<void> {}
    async close(): Promise<void> {}
    async listTools(): Promise<{ tools: Array<{ name: string }> }> {
      return { tools: ferramentas.map((name) => ({ name })) };
    }
    async callTool(req: {
      name: string;
      arguments: Record<string, unknown>;
    }): Promise<{ content: Array<{ type: string; text: string }> }> {
      chamadas.push(req);
      const corpo =
        req.name === 'get_playbook'
          ? { project: 'ragx' }
          : { results: [] };
      return { content: [{ type: 'text', text: JSON.stringify({ ok: true, data: corpo }) }] };
    }
  },
}));

const { McpRagClient } = await import('../../src/rag/McpClient');

async function conectado(tools: string[]) {
  ferramentas = tools;
  const c = new McpRagClient({ command: 'ragx', args: ['mcp'], cwd: '/proj' });
  await c.connect();
  return c;
}

const ultima = (nome: string) => [...chamadas].reverse().find((c) => c.name === nome);

beforeEach(() => {
  chamadas.length = 0;
});

describe('o teto de limit do RAGX', () => {
  it('não estoura ao derivar documentos numa instalação sem list_documents', async () => {
    const c = await conectado(['get_playbook', 'search_hybrid']);

    await c.documents();

    const busca = ultima('search_hybrid');
    expect(busca).toBeDefined();
    expect(busca!.arguments.limit).toBeLessThanOrEqual(50);
  });

  it('prefere o inventário quando o RAGX o expõe', async () => {
    const c = await conectado(['get_playbook', 'search_hybrid', 'list_documents']);

    await c.documents();

    expect(ultima('list_documents')).toBeDefined();
    expect(ultima('search_hybrid')).toBeUndefined();
  });

  it('apara qualquer busca acima do teto em vez de deixar o servidor recusar', async () => {
    const c = await conectado(['get_playbook', 'search_hybrid']);

    await c.search('qualquer', 'keyword', 500);

    expect(ultima('search_hybrid')!.arguments.limit).toBe(50);
  });
});

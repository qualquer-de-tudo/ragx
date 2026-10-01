/**
 * `build_context` devolve UMA representação do conteúdo (RAGX-0154): com
 * `format: 'markdown'` só vem `markdown`; com `format: 'json'` só vêm os
 * `fragments`. O Context Builder lê `fragments`, então o cliente tem de pedir JSON;
 * se pedisse markdown, a tela ficaria vazia.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const chamadas: Array<{ name: string; arguments: Record<string, unknown> }> = [];

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
      return { tools: [{ name: 'get_playbook' }, { name: 'build_context' }] };
    }
    async callTool(req: {
      name: string;
      arguments: Record<string, unknown>;
    }): Promise<{ content: Array<{ type: string; text: string }> }> {
      chamadas.push(req);
      const corpo =
        req.name === 'build_context'
          ? {
              project: 'ragx',
              estimated_tokens: 42,
              budget: 500,
              sources: ['a.py'],
              fragments: [
                {
                  chunk_id: 'abc',
                  document_path: 'a.py',
                  lines: [1, 9],
                  tokens: 40,
                  content: 'def f(): ...',
                  symbol: 'f',
                },
              ],
            }
          : { project: 'ragx' };
      return { content: [{ type: 'text', text: JSON.stringify({ ok: true, data: corpo }) }] };
    }
  },
}));

const { McpRagClient } = await import('../../src/rag/McpClient');

beforeEach(() => {
  chamadas.length = 0;
});

describe('build_context pelo MCP', () => {
  it('pede format json e lê os fragmentos com chunk_id e tokens', async () => {
    const c = new McpRagClient({ command: 'ragx', args: ['mcp'], cwd: '/proj' });
    await c.connect();

    const r = await c.buildContext('autenticação', 500);

    const pedido = chamadas.find((x) => x.name === 'build_context');
    expect(pedido!.arguments.format).toBe('json');
    expect(pedido!.arguments.response_format).toBe('detailed');
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.data.fragments).toHaveLength(1);
      expect(r.data.fragments[0]).toMatchObject({ chunkId: 'abc', tokens: 40, documentPath: 'a.py' });
      expect(r.data.estimatedTokens).toBe(42);
    }
  });
});

/**
 * `get_entity` (Tasks 1-3) passou a devolver `confidence`/`source`/`tier` na
 * entidade e em cada relação. Este teste existe para que o mapeamento do
 * transporte MCP pare de jogar esses campos fora ao montar `EntityDetail`.
 */

import { describe, expect, it, vi } from 'vitest';

let ultimaResposta: Record<string, unknown> = {};

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
      return { tools: ['get_playbook', 'get_entity'].map((name) => ({ name })) };
    }
    async callTool(req: {
      name: string;
      arguments: Record<string, unknown>;
    }): Promise<{ content: Array<{ type: string; text: string }> }> {
      const corpo = req.name === 'get_playbook' ? { project: 'ragx' } : ultimaResposta;
      return { content: [{ type: 'text', text: JSON.stringify({ ok: true, data: corpo }) }] };
    }
  },
}));

const { McpRagClient } = await import('../../src/rag/McpClient');

describe('confidence e tier na entidade e nas relacoes', () => {
  it('nao descarta confidence/source/tier vindos do MCP', async () => {
    ultimaResposta = {
      entity: {
        id: 'e1', name: 'AuthService', type: 'class', qualified_name: 'auth.py::AuthService',
        confidence: 1.0, source: 'structural', tier: 'extracted',
      },
      relations: [
        {
          type: 'uses', direction: 'out', other: 'Redis', other_type: 'technology',
          confidence: 0.75, source: 'reference', tier: 'inferred',
        },
      ],
      sources: [],
    };
    const client = new McpRagClient({ command: 'ragx', args: ['mcp'], cwd: '/proj' });
    await client.connect();
    const r = await client.entity('AuthService');
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.data.entity.tier).toBe('extracted');
    expect(r.data.relations[0].tier).toBe('inferred');
  });
});

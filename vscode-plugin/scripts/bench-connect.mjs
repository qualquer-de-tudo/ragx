/**
 * Benchmark do caminho REAL de conexão VS Code -> RAGX.
 *
 * Reproduz, passo a passo, o que `McpRagClient.connect()` faz — spawn do
 * processo, handshake MCP, listagem de ferramentas e a primeira chamada. Medir
 * o cliente de verdade é o que impede otimizar a etapa errada: sem isto,
 * "está lento" não diz se o custo é do Python, do transporte ou da primeira
 * consulta.
 *
 *   node scripts/bench-connect.mjs --cmd ragx --cwd /caminho/do/projeto -n 5
 *
 * Imprime JSON com a mediana de cada etapa. Mediana, não média: um pico de
 * antivírus no primeiro spawn não pode virar "a conexão regrediu".
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

function arg(nome, padrao) {
  const i = process.argv.indexOf(nome);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : padrao;
}

const command = arg('--cmd', 'ragx');
const cwd = arg('--cwd', process.cwd());
const rodadas = Number(arg('-n', '5'));
const serveArgs = (arg('--args', 'mcp,serve,--read-only')).split(',');
/** Primeira chamada medida. É a que a extensão faz para descobrir o projeto. */
const primeira = arg('--first-call', 'get_playbook');

function mediana(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2);
}

async function umaRodada() {
  const etapas = {};
  const t0 = performance.now();

  const transport = new StdioClientTransport({ command, args: serveArgs, cwd, stderr: 'pipe' });
  const client = new Client({ name: 'ragx-bench', version: '0' }, { capabilities: {} });

  let s = performance.now();
  await client.connect(transport);
  // Spawn, boot do Python e o `initialize` do MCP chegam juntos: o SDK não
  // expõe a fronteira entre eles, e fingir que expõe seria inventar número.
  etapas.spawn_boot_handshake_ms = Math.round(performance.now() - s);

  s = performance.now();
  const listed = await client.listTools();
  etapas.list_tools_ms = Math.round(performance.now() - s);

  s = performance.now();
  await client.callTool({ name: primeira, arguments: {} });
  etapas.first_call_ms = Math.round(performance.now() - s);

  // Segunda chamada igual à primeira: mostra quanto do custo era boot preguiçoso
  // do servidor e quanto é o trabalho em si.
  s = performance.now();
  await client.callTool({ name: primeira, arguments: {} });
  etapas.second_call_ms = Math.round(performance.now() - s);

  etapas.total_ready_ms = Math.round(performance.now() - t0);
  await client.close();
  return { etapas, tools: listed.tools.length };
}

const amostras = [];
let tools = 0;
for (let i = 0; i < rodadas; i++) {
  const r = await umaRodada();
  amostras.push(r.etapas);
  tools = r.tools;
  process.stderr.write(`rodada ${i + 1}/${rodadas}: ${r.etapas.total_ready_ms}ms\n`);
}

const chaves = Object.keys(amostras[0]);
const saida = { command, cwd, rodadas, tools, mediana_ms: {}, amostras };
for (const k of chaves) saida.mediana_ms[k] = mediana(amostras.map((a) => a[k]));
console.log(JSON.stringify(saida, null, 2));
process.exit(0);

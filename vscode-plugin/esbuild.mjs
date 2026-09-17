/**
 * Bundle do extension host.
 *
 * Um arquivo só, CommonJS, com `vscode` externo (o VS Code injeta em runtime).
 * O `.vsix` sai com `--no-dependencies`: sem bundle, ele carregaria a árvore
 * inteira de node_modules e passaria de dezenas de megabytes.
 */
import { readFileSync } from 'node:fs';

import esbuild from 'esbuild';

// A versão vem do package.json, não de um literal no código. A cópia que
// existia em `McpClient.ts` — anunciada ao servidor MCP no handshake —
// dependia de alguém lembrar de bumpar dois arquivos no mesmo commit.
const { version } = JSON.parse(readFileSync('./package.json', 'utf8'));

const producao = process.argv.includes('--production');
const watch = process.argv.includes('--watch');

const opcoes = {
  entryPoints: ['src/extension.ts'],
  bundle: true,
  outfile: 'dist/extension.js',
  platform: 'node',
  target: 'node20',
  format: 'cjs',
  external: ['vscode'],
  sourcemap: !producao,
  minify: producao,
  logLevel: 'info',
  define: { __RAGX_VERSION__: JSON.stringify(version) },
};

if (watch) {
  const ctx = await esbuild.context(opcoes);
  await ctx.watch();
} else {
  await esbuild.build(opcoes);
}

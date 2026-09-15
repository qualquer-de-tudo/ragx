/**
 * Build da webview.
 *
 * Saída com nomes FIXOS (`index.js`, `index.css`) porque o HTML é montado no
 * extension host, que precisa saber o caminho sem ler um manifesto. Sem hash
 * no nome também evita lixo acumulado em `dist/webview` entre builds.
 *
 * `inlineDynamicImports` porque a CSP só libera um script com nonce: um chunk
 * carregado dinamicamente seria bloqueado em silêncio.
 */
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  root: 'webview',
  plugins: [react()],
  build: {
    outDir: '../dist/webview',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: 'index.js',
        assetFileNames: 'index.[ext]',
        inlineDynamicImports: true,
      },
    },
  },
});

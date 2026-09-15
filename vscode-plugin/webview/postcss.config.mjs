/**
 * O caminho do config do Tailwind é explícito porque ele é `.ts`: sem isto o
 * PostCSS procura `tailwind.config.js`, não acha, e gera um CSS sem nenhuma
 * das classes — o build passa e a UI sai sem estilo.
 */
import { fileURLToPath } from 'node:url';

export default {
  plugins: {
    tailwindcss: {
      config: fileURLToPath(new URL('./tailwind.config.ts', import.meta.url)),
    },
    autoprefixer: {},
  },
};

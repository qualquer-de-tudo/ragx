/**
 * Tailwind sobre as variáveis de tema do VS Code.
 *
 * Nenhuma cor literal aqui. Light, Dark e High Contrast saem de graça porque a
 * paleta inteira é `var(--vscode-*)` — impor um tema próprio quebraria alto
 * contraste, que é exatamente quem mais precisa que não quebre (§29).
 */
import { fileURLToPath } from 'node:url';

import type { Config } from 'tailwindcss';

/**
 * Caminhos ABSOLUTOS de propósito: o Tailwind resolve `content` contra o
 * diretório de trabalho do processo, não contra este arquivo. Com globs
 * relativos, o build roda a partir da raiz do plugin, não encontra nada, e
 * gera um CSS só com o preflight — sem erro nenhum.
 */
const aqui = (rel: string) => fileURLToPath(new URL(rel, import.meta.url));

/** Atalho para as variáveis que o VS Code injeta na webview. */
const vsc = (nome: string) => `var(--vscode-${nome})`;

export default {
  content: [aqui('./index.html'), aqui('./src/**/*.{ts,tsx}')],
  theme: {
    extend: {
      colors: {
        fg: vsc('foreground'),
        'fg-muted': vsc('descriptionForeground'),
        bg: vsc('editor-background'),
        'bg-side': vsc('sideBar-background'),
        'bg-input': vsc('input-background'),
        'fg-input': vsc('input-foreground'),
        border: vsc('panel-border'),
        'border-input': vsc('input-border'),
        focus: vsc('focusBorder'),
        link: vsc('textLink-foreground'),
        'link-active': vsc('textLink-activeForeground'),
        btn: vsc('button-background'),
        'btn-fg': vsc('button-foreground'),
        'btn-hover': vsc('button-hoverBackground'),
        'btn-sec': vsc('button-secondaryBackground'),
        'btn-sec-fg': vsc('button-secondaryForeground'),
        hover: vsc('list-hoverBackground'),
        active: vsc('list-activeSelectionBackground'),
        'active-fg': vsc('list-activeSelectionForeground'),
        badge: vsc('badge-background'),
        'badge-fg': vsc('badge-foreground'),
        ok: vsc('testing-iconPassed'),
        warn: vsc('editorWarning-foreground'),
        err: vsc('editorError-foreground'),
        info: vsc('editorInfo-foreground'),
        code: vsc('textCodeBlock-background'),
        progress: vsc('progressBar-background'),
      },
      fontFamily: {
        sans: [vsc('font-family')],
        mono: [vsc('editor-font-family'), 'monospace'],
      },
      fontSize: {
        base: vsc('font-size'),
      },
      borderRadius: {
        DEFAULT: '3px',
      },
    },
  },
  plugins: [],
} satisfies Config;
